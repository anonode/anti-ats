import re, os
import torch 
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from functools import lru_cache
from pathlib import Path
from datetime import datetime
import docx2txt
import fitz
import nltk
from nltk.corpus import stopwords
from transformers import BertTokenizer, BertModel 
import textstat
import json


class TextPreprocessor:
    def __init__(self):
        self.stop_words = frozenset(stopwords.words('english'))
        self.tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
        self.model = BertModel.from_pretrained("bert-base-uncased")
        
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
        sentences = nltk.tokenize.sent_tokenize(text)
        sentence_embeddings = []

        for sentence in sentences:
            inputs = self.tokenizer(text, return_tensors = "pt", padding = True, truncation = True)
            
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            sentence_embedding = outputs.last_hidden_state.mean(dim = 1) # take an average accross all token embeddings for sentence-level embeddings
            sentence_embeddings.append(sentence_embedding)

        return sentences, sentence_embeddings # MrClean 

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


    def extract_keywords(self, text: str) -> dict[str, float]:
        if text in self.cache:
            return self.cache[text]
            
        pText = self.preprocessor.pptxt(text)
        
        tokens = self.preprocessor.tokenizer.tokenize(pText)
        
        mergedTokens = []
        word = ''

        for token in tokens:
            if token.startswith('##'):
                word += token[2:] # Remove all hashtags that define subwords like ##ing and append the subword
            else:
                if word:
                    mergedTokens.append(word)
                word = token 
        
        # This is to fix the bug of the last word not being added
        if word:
            mergedTokens.append(word)
        
        tfVec = TfidfVectorizer(ngram_range = (1,4), stop_words = 'english')
        tfMatrix = tfVec.fit_transform([' '.join(mergedTokens)])

        tfScores = dict(zip(tfVec.get_feature_names_out(), tfMatrix.toarray()[0]))

        keywords = {ngram: score for ngram, score in sorted(tfScores.items(), key = lambda item: item[1], reverse = True)}

        # Normalizing frequencies could help keyword matching accuracy so if keyword matching sucks use this code
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
        self.sample_skills = { # Provides list of common skills for quicker recognition
            'python', 'java', 'javascript', 'c++', 'ruby', 'php', 'sql',
            'html', 'css', 'aws', 'azure', 'docker', 'kubernetes', 'linux',
            'windows', 'git', 'agile', 'scrum', 'ci/cd', 'rest', 'api',
            'machine learning', 'artificial intelligence', 'data science',
            'data analysis', 'cloud computing', 'database', 'nodejs'
        }
        
    def skillExtractor(self, text: str) -> set[str]:
        tokens = self.preprocessor.tokenizer.tokenize(text.lower())
        skills = set()

        for token in tokens:
            if token in self.sample_skills:
                skills.add(token)

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
        sentences, _ = self.preprocessor.extract_sentences(text)
        if not sentences:
            return {
                "score": 0.0,
                "avg_sentence_length": 0.0,
                "cw_ratio": 0.0
            }
            
        words = text.split() 
        avg_sentence_length = len(words) / len(sentences) 
        
        # Calculation for complex words updated to use textstat instead of my previous created function
        complex_words = sum(1 for word in words if textstat.syllable_count(word) > 2) 
        cw_ratio = complex_words / len(words) if words else 0
        
        score = 100 - (avg_sentence_length * 0.5 + cw_ratio * 30)
        score = max(0, min(100, score))
        
        return {
            "score": score,
            "avg_sentence_length": avg_sentence_length,
            "cw_ratio": cw_ratio
        }
    
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
        
        # Convert sets to lists for JSON serialization
        matched_skills_list = list(rSkills.intersection(jSkills))
        missing_skills_list = list(jSkills - rSkills)
        
        return {
            "overall_score": round(overall_score, 2),
            "match_score": round(keyword_scores["match score"], 2),
            "skill_match": round(skill_score, 2),
            "readability": round(readability_metrics["score"], 2),
            "matched_skills": matched_skills_list,
            "missing_skills": missing_skills_list,
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
        """
        Process a resume file and job description to return ATS compatibility scores as a dictionary.
        
        Args:
            file_path (str): Path to the resume file
            jobDesc (str): Job description text
            file_type (str, optional): Type of resume file ('pdf' or 'docx'). Defaults to "pdf".
            job_type (str, optional): Type of job ('technical', 'management', or 'general'). Defaults to "general".
            
        Returns:
            dict: A dictionary containing ATS scoring results
        """
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
    
    def get_ats_results(self, file_path: str, jobDesc: str,
                      file_type: str = "pdf", job_type: str = "general") -> dict:
        """
        Get ATS results in a structured JSON-friendly format
        
        Args:
            file_path (str): Path to the resume file
            jobDesc (str): Job description text
            file_type (str, optional): Type of resume file ('pdf' or 'docx'). Defaults to "pdf".
            job_type (str, optional): Type of job ('technical', 'management', or 'general'). Defaults to "general".
            
        Returns:
            dict: A JSON-friendly dictionary with formatted ATS results
        """
        try:
            results = self.resCheck(file_path, jobDesc, file_type, job_type)
            
            # Create a result structure that's formatted nicely for the user
            formatted_results = {
                "success": True,
                "results": {
                    "summary": {
                        "overall_score": results['overall_score'],
                        "keyword_match": results['match_score'],
                        "skill_match": results['skill_match'],
                        "readability": results['readability']
                    },
                    "skills": {
                        "matched": results['matched_skills'],
                        "missing": results['missing_skills']
                    },
                    "keywords": {
                        "frequencies": results['detailed_metrics']['kw_freq']
                    },
                    "readability_metrics": {
                        "avg_sentence_length": results['detailed_metrics']['avg_sentence_length'],
                        "complex_word_ratio": results['detailed_metrics']['cw_ratio']
                    },
                    "metadata": results['metadata']
                }
            }
            
            return formatted_results
            
        except FileNotFoundError as e:
            return {
                "success": False,
                "error": {
                    "type": "FileNotFoundError",
                    "message": str(e)
                }
            }
        except ValueError as e:
            return {
                "success": False,
                "error": {
                    "type": "ValueError", 
                    "message": str(e)
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": {
                    "type": "Exception",
                    "message": str(e)
                }
            }


# Example usage
def analyze_resume(resume_path: str, job_description: str, file_type: str = "pdf", job_type: str = "technical") -> dict:
    """
    Analyze a resume against a job description and return structured results.
    
    Args:
        resume_path (str): Path to the resume file
        job_description (str): Job description text
        file_type (str, optional): Type of resume file ('pdf' or 'docx'). Defaults to "pdf".
        job_type (str, optional): Type of job ('technical', 'management', or 'general'). Defaults to "technical".
        
    Returns:
        dict: A dictionary containing the ATS analysis results
    """
    checker = ATSChecker()
    return checker.get_ats_results(
        file_path=resume_path,
        jobDesc=job_description,
        file_type=file_type,
        job_type=job_type
    )


# Can be used if you want to maintain the original functionality, 
# but with results returned as a JSON string instead of printing
def main():
    try:
        checker = ATSChecker()
        
        # Both variables below are for testing and should be changed to user input
        resume_path = "/home/zay/Downloads/Izaiah Fleming Resume 2025.pdf"
        jobDesc = """ 
        The Software Engineering Intern will be a passionate, opinionated and creative individual who can develop web applications from the ground up. You will understand web strengths and constraints and build pixel perfect solutions. You should be capable, and willing, to assist in developing responsive single-page web applications.

        Develop efficient, secure applications, peer-review code, and document solutions within an agile-blended software environment
        Collaborate with other senior engineers, and management, to achieve optimal application design
        Communicate proactively with teammates, infrastructure, security, and quality assurance to continuously improve processes and engineering excellence
        Work on Web based applications and Services utilizing Java, Spring, Hibernate, AngularJS and Java Script.
        Learn quickly and be productive in a highly collaborative, lightning-fast environment.
        Follow and Promote best practices in Software Development
        Experience developing cutting edge applications
        Experience designing and building single page applications using any Javascript Framework.
        Knowledge in at least one client side MVC JavaScript framework (preferably ReactJS or ReactNative)
        Experience developing modular front-end components and building web experiences using HTML5, CSS3, JavaScript
        Knowledge of web standards, cross-browser compatibility and constraints of the web
        Understanding of browser rendering behavior and performance
        Good written and communication skills
        Experience with Agile methodologies
        Completed Bachelor's Degree in Computer Science
        """
        
        results = checker.get_ats_results(
            file_path=resume_path,
            jobDesc=jobDesc,
            file_type="pdf",
            job_type="technical"
        )
        
        # Convert to JSON string with nice formatting
        json_results = json.dumps(results, indent=2)
        print(json_results)
        
        return results  # Also return the results dictionary for programmatic use
    
    except Exception as e:
        error_results = {
            "success": False,
            "error": {
                "type": type(e).__name__,
                "message": str(e)
            }
        }
        print(json.dumps(error_results, indent=2))
        return error_results


if __name__ == "__main__":
    main()