import re, os
from functools import lru_cache
from pathlib import Path
from datetime import datetime
import docx2txt
import fitz
from nltk.corpus import stopwords
import spacy

class TextPreprocessor:
    def __init__(self):
        self.stop_words = frozenset(stopwords.words('english'))
        self.nlp = spacy.load("en_core_web_md") # might need to switch to large model instead for proper word vectors
        
    @lru_cache(maxsize=128) # Used to speed up performance (if same text is processed multiple times) by caching results for up to n unique inputs 
    def pptxt(self, text: str) -> str: # Pre-process txt WITHOUT stemming (Stemming negatively effects keywords)
        text = ' '.join(text.lower().split())
        
        # Remove unrelated stuff like emails, URLs, and special characters that arent related to numbers or "important" punctuation
        text = re.sub(r'\S+@\S+', '', text)
        text = re.sub(r'http\S+|www\S+', '', text)
        text = re.sub(r'[^a-zA-Z0-9\s\.\-]', '', text)
        
        # Split text up into words and remove any "stopwords" (i.e A, An, The, And, But)
        words = [
            word 
            for word in text.split() 
            if word not in self.stop_words
        ]
        
        return ' '.join(words) # Join all words back together into single string
    
    def extract_sentences(self, text: str) -> list[str]:
        doc = self.nlp(text) # Parses text into "tokens" and sentences 
        return [sent.text.strip() for sent in doc.sents] # Returns a cleaned list of sentence strings

class DocumentParser:
    @staticmethod
    def extractPDF(file_path: str) -> str:
        try:
            with fitz.open(file_path) as doc: # Open pdf 
                text = []
                for page in doc: # Iterate and append each page to text[]
                    text.append(page.get_text())
                    
                    # Checks for tables and attempts to extract all text from them
                    tables = page.find_tables()
                    for table in tables:
                        text.extend([cell.text for cell in table.cells])
                        
                return ' '.join(text)
        except Exception as e:
            raise ValueError(f"Failed to process PDF file: {str(e)}")

    @staticmethod
    def extractDocx(file_path: str) -> str:
        try:
            return docx2txt.process(file_path)
        except Exception as e:
            raise ValueError(f"Failed to process DOCX file: {str(e)}")

class KeywordExtractor: 
    def __init__(self, preprocessor: TextPreprocessor):
        self.preprocessor = preprocessor
        self.cache: dict[str, dict[str, float]] = {} # Cache to help with repeated calls 

    # Helper function that probably needs some work but currently it makes it to where we dont have stupid long sentences for no reason
    def isSentence(self, phrase: str) -> bool:
        if len(phrase.split()) > 6 or phrase.endswith(('.', '!', '?')):
            return True
        return False
        
    def extract_keywords(self, text: str) -> dict[str, float]:
        if text in self.cache:
            return self.cache[text]
            
        pText = self.preprocessor.pptxt(text)
        doc = self.preprocessor.nlp(pText)
        
        keywords = {}
        
        # Process nouns to look for multi-word phrases (i.e software engineering, machine learning)
        for chunk in doc.noun_chunks:
            phrase = chunk.text.lower()

            if len(phrase.split()) > 1 and not phrase.endswith('.'): # this is kinda a monkey version of solving this issue needs change for sure
                if not self.isSentence(phrase): 
                    keywords[phrase] = keywords.get(phrase, 0) + 1
        
        # Check each token for its relevancy and increments a counter for each relevant token
        for token in doc:
            if (not token.is_stop and not token.is_punct 
                and not token.is_space and len(token.text) > 1):
                word = token.text.lower()
                keywords[word] = keywords.get(word, 0) + 1
        
        # Normalize frequencies
        max_freq = max(keywords.values()) if keywords else 1
        kw_Weight = {
            word: (freq / max_freq) 
            for word, freq in keywords.items()
        }
        
        self.cache[text] = kw_Weight
        return kw_Weight

class SkillMatcher:
    def __init__(self, preprocessor: TextPreprocessor):
        self.preprocessor = preprocessor
        self.nlp = preprocessor.nlp
        self.sample_skills = { # Provides list of common skills for quicker recognition
            'python', 'java', 'javascript', 'c++', 'ruby', 'php', 'sql',
            'html', 'css', 'aws', 'azure', 'docker', 'kubernetes', 'linux',
            'windows', 'git', 'agile', 'scrum', 'ci/cd', 'rest', 'api',
            'machine learning', 'artificial intelligence', 'data science',
            'data analysis', 'cloud computing', 'database', 'nodejs'
        }
        
    def skillExtractor(self, text: str) -> set[str]:
        doc = self.nlp(text.lower())
        skills = set()
        
        # Extract noun phrases
        for chunk in doc.noun_chunks:
            phrase = chunk.text.lower()
            if phrase in self.sample_skills:
                skills.add(phrase)
            for word in phrase.split(): # Check individual words (Incase there is a single word skill term)
                if word in self.sample_skills:
                    skills.add(word)
        
        # Check for skills in the text that might not be in noun chunks
        text_lower = text.lower()
        for skill in self.sample_skills:
            if skill in text_lower:
                skills.add(skill)
        
        return skills
        
    def calc_skillscore(self, rSkills: set[str], jSkills: set[str]) -> float: # Use basic fuzzy matching to calc skill score between a resume and job desc (prob gotta change this to Levenshtein or Winkler)
        if not jSkills:
            return 0.0
        
        matches = 0
        for jSkill in jSkills:
            if jSkill in rSkills:
                matches += 1
                continue
                
            # Check for partial matches (i.e python in (programming python))
            for rSkill in rSkills:
                if (jSkill in rSkill or rSkill in jSkill):
                    matches += 0.5
                    break
        
        return (matches / len(jSkills)) * 100 

class ReadabilityAnalyzer:
    def __init__(self, preprocessor: TextPreprocessor):
        self.preprocessor = preprocessor
        
    def calc_readability(self, text: str) -> dict[str, float]:
        sentences = self.preprocessor.extract_sentences(text)
        if not sentences:
            return {
                "score": 0.0,
                "avg_sentence_length": 0.0,
                "cw_ratio": 0.0
            }
            
        words = text.split() 
        avg_sentence_length = len(words) / len(sentences) 
        
        # Calculation for if words have more than 2 syllables (This is what would make them "complex" it is not a good thing to have too many complex words)
        complex_words = sum(1 for word in words if self.count_syllables(word) > 2) 
        cw_ratio = complex_words / len(words) if words else 0
        
        score = 100 - (avg_sentence_length * 0.5 + cw_ratio * 30)
        score = max(0, min(100, score))
        
        return {
            "score": score,
            "avg_sentence_length": avg_sentence_length,
            "cw_ratio": cw_ratio
        }
    
    # Lowkey probably unneccessary will probably replace this implementation (Likely with something like textstat)
    @staticmethod
    def count_syllables(word: str) -> int:
        word = word.lower()
        count = 0
        vowels = 'aeiouy'
        on_vowel = False
        
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not on_vowel:
                count += 1
            on_vowel = is_vowel
            
        if word.endswith('e'):
            count -= 1
        if count == 0:
            count = 1
            
        return count
    
class ATSScorer:
    def __init__(self):
        self.preprocessor = TextPreprocessor()
        self.keyword_extractor = KeywordExtractor(self.preprocessor)
        self.skill_matcher = SkillMatcher(self.preprocessor)
        self.RA = ReadabilityAnalyzer(self.preprocessor)
        
    def calc_scores(self, resume_text: str, 
                        job_description: str,
                        job_type: str = "general") -> dict:
        keyword_scores = self.calc_kw_score(resume_text, job_description)
        
        rSkills = self.skill_matcher.skillExtractor(resume_text)
        jSkills = self.skill_matcher.skillExtractor(job_description)
        skill_score = self.skill_matcher.calc_skillscore(rSkills, jSkills)
        
        readability_metrics = self.RA.calc_readability(resume_text)
        
        weights = self.getWeight(job_type)
        
        overall_score = (
            weights["keyword"] * keyword_scores["match score"] +
            weights["skill"] * skill_score +
            weights["readability"] * readability_metrics["score"]
        )
        
        return {
            "overall_score": round(overall_score, 2),
            "match score": round(keyword_scores["match score"], 2),
            "skill_match": round(skill_score, 2),
            "readability": round(readability_metrics["score"], 2),
            "matched_skills": rSkills.intersection(jSkills),
            "missing_skills": jSkills - rSkills,
            "detailed_metrics": {
                "kw_freq": keyword_scores["kw_freq"],
                "avg_sentence_length": round(readability_metrics["avg_sentence_length"], 2),
                "cw_ratio": round(readability_metrics["cw_ratio"], 2)
            }
        }
        
    def calc_kw_score(self, resume_text: str, jobDesc: str) -> dict:
        res_keywords = self.keyword_extractor.extract_keywords(resume_text)
        job_keywords = self.keyword_extractor.extract_keywords(jobDesc)
        
       
        totalWeight = sum(job_keywords.values())
        matched_weight = 0
        
        kw_freq = {} 
        
        for job_word, job_weight in job_keywords.items():
            best_match_score = 0
            
            # Check for both exact and partial matches 
            for resume_word, resume_weight in res_keywords.items():
                if job_word == resume_word:
                    best_match_score = resume_weight
                    kw_freq[job_word] = resume_weight
                    break
                elif (job_word in resume_word or resume_word in job_word):
                    match_score = 0.5 * resume_weight
                    best_match_score = max(best_match_score, match_score)
                    if match_score > 0:
                        kw_freq[job_word] = resume_weight
            
            matched_weight += min(job_weight, best_match_score)
        
        match_score = (matched_weight / totalWeight * 100) if totalWeight else 0
        
        return {
            "match score": match_score,
            "kw_freq": kw_freq
        }
        
    @staticmethod
    def getWeight(job_type: str) -> dict[str, float]: 
        weights = {
            "technical": {
                "keyword": 0.4,
                "skill": 0.4,
                "readability": 0.2
            },
            "management": {
                "keyword": 0.3,
                "skill": 0.3,
                "readability": 0.4
            },
            "general": {
                "keyword": 0.35,
                "skill": 0.35,
                "readability": 0.3
            }
        }
        return weights.get(job_type, weights["technical"])

class ATSChecker: 
    def __init__(self):
        self.document_parser = DocumentParser()
        self.scorer = ATSScorer()
        
    def resCheck(self, file_path: str, jobDesc: str,
                    file_type: str = "pdf", job_type: str = "general") -> dict:
            # File validation
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Resume file not found: {file_path}")
            if not jobDesc:
                raise ValueError("Job description cannot be empty")
                
            # Check file type then extract text
            if file_type.lower() == "pdf":
                resText = self.document_parser.extractPDF(file_path)
            elif file_type.lower() == "docx":
                resText = self.document_parser.extractDocx(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
                
            scores = self.scorer.calc_scores(resText, jobDesc, job_type)
            
            scores["metadata"] = {
                "timestamp": datetime.now().isoformat(),
                "file_name": Path(file_path).name,
                "file_type": file_type 
            }
            
            return scores



def ats_results():
    try:
        checker = ATSChecker()
        
        # Both variables below are for testing and should be changed to user input
        resume_path = "C:\\Users\\roliv\Code\\anti-ats\\app\\RichardOlivarri.pdf"
        jobDesc = """ 
        Python Developer Position
        
        Requirements:
        Bachelor Degree in Computer Science, Software engineering, or equivalent.
        Strong planning, organizational, analytical, interpersonal, decision making, oral and written communication skills strongly preferred. 
        Software development experience is a must. C# or Python experience is preferred.
        Database experience (Postgres, MySql, etc ) is preferred.
        Familiarity with DOD Software practices, systems, and publications is helpful.
        Thorough knowledge of MS Office product suite (Excel, Access, Word, PowerPoint).
        Ability to understand company instruction, company process and quality manuals.
        Must be a US Citizen. Make this into a single sentence for me
        
        Responsibilities:
        Develop cloud hosted applications 
        Provide support to the deployment, automation, management, and maintenance of AWS production applications.
        Develop and deploy fully functional architecture and tools to the AWS cloud 
        Support the development and migration of web applications to the cloud (Ideally AWS Govcloud and/or Cloud One) 
        Troubleshooting and problem solving across different application domains and platforms.
        Pre-deployment acceptance testing.
        Carry out and/or oversee critical system security testing.
        Analyze and provide recommendations for architecture and process improvements.
        Deployment of metrics, logging, and monitoring systems on AWS platform.
        Design, maintenance and management tools for automation of different operational processes.
        Participates in projects as a team member and/or team project leader.
        Coordinates activities with the Manager of Engineering.
        Manages approved project timelines. Produces periodic project status reports comparing actual to forecasted timeline.
        Writes detailed technical reports to document information related to the understanding of relevant failure modes and the results of reliability analyses, prepares proposals & develops work instructions. Prepares and delivers presentations of analysis results to appropriate staff and customers.
        Carries out special duties as assigned.
        Performs other related duties as assigned.
        """
        
        results = checker.resCheck(
            file_path = resume_path,
            jobDesc = jobDesc,
            file_type = "pdf",
            job_type = "technical"
        )
    
        print("===============================\nATS Scan Results \n===============================")
        print(f"\nOverall Score: {results['overall_score']}%")
        print("\nDetailed Scores:")
        print(f"- Keyword Match: {results['match score']}%")
        print(f"- Skill Match: {results['skill_match']}%")
        print(f"- Readability: {results['readability']}%")
        
        print("-------------------------------\nSkill Analysis \n-------------------------------")
        print("\nMatched Skills:")
        for skill in results['matched_skills']:
            print(f"✓ {skill}")
        
        print("\nMissing Skills:")
        for skill in results['missing_skills']:
            print(f"* {skill}")
        
        print("\nKeyword Frequency:")
        for keyword, frequency in results['detailed_metrics']['kw_freq'].items():
            print(f"- {keyword}: {frequency:.2f}")
        
        print("\nReadability Metrics:")
        print(f"- Average Sentence Length: {results['detailed_metrics']['avg_sentence_length']:.2f} words")
        print(f"- Complex Word Ratio: {results['detailed_metrics']['cw_ratio']:.2%}")
        
        print("\nDocument Metadata:")
        print(f"- File: {results['metadata']['file_name']}")
        print(f"- Type: {results['metadata']['file_type']}")
        print(f"- Analysis Time: {results['metadata']['timestamp']}")
            
    except FileNotFoundError as e:
        print(f"\nError: Could not find resume file - {str(e)}")
    except ValueError as e:
        print(f"\nError: Invalid input - {str(e)}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {str(e)}")
        raise