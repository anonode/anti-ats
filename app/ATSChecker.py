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
            # Programming Languages
            'python', 'java', 'javascript', 'typescript', 'c', 'c++', 'cplusplus', 'c#', 'csharp', 'ruby', 'php', 'go', 'golang',
            'rust', 'kotlin', 'swift', 'objective-c', 'perl', 'scala', 'r', 'matlab', 'bash', 'powershell', 'shell script',
            'groovy', 'dart', 'fortran', 'cobol', 'haskell', 'lisp', 'lua', 'erlang', 'clojure', 'f#', 'fsharp',
            'solidity', 'assembly', 'vba', 'vb.net', 'vbnet', 'basic', 'apex', 'actionscript', 'shell', 'sql',
            
            # Web Development
            'html', 'css', 'sass', 'scss', 'less', 'bootstrap', 'tailwind', 'html5', 'css3', 'jquery', 'materialize',
            'bulma', 'foundation', 'semantic ui', 'stylus', 'postcss', 'webpack', 'vite', 'parcel', 'gulp', 'grunt',
            'babel', 'rollup', 'webassembly', 'wasm', 'pwa', 'amp', 'ssr', 'ssg', 'jamstack', 'web components',
            'webgl', 'web3', 'responsive design', 'wcag', 'a11y', 'accessibility', 'web accessibility',
            
            # JavaScript Frameworks/Libraries
            'react', 'angular', 'vue', 'svelte', 'ember', 'backbone', 'next.js', 'nextjs', 'nuxt.js', 'nuxtjs', 
            'node.js', 'nodejs', 'deno', 'express', 'nestjs', 'redux', 'mobx', 'jquery', 'react native', 'electron',
            'meteor', 'gatsby', 'preact', 'stimulus', 'solid', 'lit', 'alpine', 'aurelia', 'ember.js', 'emberjs',
            'rxjs', 'zustand', 'recoil', 'jotai', 'xstate', 'graphql', 'apollo', 'relay', 'urql', 'swr', 'react query',
            'tanstack query', 'three.js', 'threejs', 'd3', 'd3.js', 'chart.js', 'chartjs', 'highcharts', 'echarts',
            
            # Back-end Frameworks
            'django', 'flask', 'fastapi', 'spring', 'spring boot', 'hibernate', 'laravel', 'symfony', 'rails',
            'asp.net', 'aspnet', '.net core', '.net', 'dotnet', 'core', 'dotnet core', 'struts', 'play framework',
            'tornado', 'sanic', 'bottle', 'falcon', 'pyramid', 'sinatra', 'express.js', 'expressjs', 'koa', 'hapi',
            'adonis', 'fastify', 'phoenix', 'cakephp', 'codeigniter', 'yii', 'zend', 'slim', 'vapor', 'lumen',
            'quarkus', 'micronaut', 'ktor', 'gin', 'echo', 'beego', 'catalyst', 'dancer', 'mojolicious',
            
            # Databases & Data Storage
            'sql', 'mysql', 'postgresql', 'postgres', 'sqlite', 'oracle', 'sql server', 'sqlserver', 'ssms',
            'mongodb', 'dynamodb', 'cassandra', 'redis', 'memcached', 'elasticsearch', 'neo4j', 'couchdb', 'mariadb',
            'firebase', 'cosmosdb', 'nosql', 'no sql', 'graph database', 'key-value', 'keyvalue', 'time series',
            'influxdb', 'timescaledb', 'cockroachdb', 'yugabytedb', 'snowflake', 'bigquery', 'redshift', 'athena',
            'presto', 'trino', 'clickhouse', 'hbase', 'couchbase', 'bigtable', 'riak', 'etcd', 'scylla', 'faunadb',
            'realm', 'greenplum', 'teradata', 'pouchdb', 'realm', 'typeorm', 'sequelize', 'mongoose', 'prisma',
            'liquibase', 'flyway', 'rdbms', 'orm', 'odm', 'data warehouse', 'data mart', 'data lake', 'delta lake',
            'iceberg', 'hudi', 'lakehouse', 'acid', 'base', 'cap theorem', 'sharding', 'replication', 'partitioning',
            
            # Cloud Platforms
            'aws', 'amazon web services', 'azure', 'microsoft azure', 'google cloud', 'gcp', 'heroku',
            'digital ocean', 'digitalocean', 'ibm cloud', 'openstack', 'alibaba cloud', 'oracle cloud',
            'cloudflare', 'vercel', 'netlify', 'firebase', 'aws lambda', 'ec2', 's3', 'rds', 'dynamodb',
            'sqs', 'sns', 'kinesis', 'cloudwatch', 'cloudfront', 'route53', 'iam', 'vpc', 'ecs', 'eks',
            'fargate', 'beanstalk', 'azure functions', 'azure vm', 'azure ad', 'azure devops', 'azure blob',
            'cosmos db', 'app service', 'gcp functions', 'cloud run', 'gke', 'bigquery', 'dataflow', 'dataproc',
            'pub/sub', 'firebase', 'cloud storage', 'terraform', 'pulumi', 'cloudformation', 'arm templates',
            'serverless', 'faas', 'iaas', 'paas', 'saas',
            
            # DevOps & Tools
            'docker', 'kubernetes', 'k8s', 'jenkins', 'gitlab ci', 'github actions', 'travis ci',
            'terraform', 'ansible', 'puppet', 'chef', 'prometheus', 'grafana', 'elk stack', 'elk', 'ci/cd', 'cicd',
            'continuous integration', 'continuous deployment', 'continuous delivery', 'argocd', 'spinnaker', 'tekton',
            'github', 'gitlab', 'bitbucket', 'circleci', 'buildkite', 'drone', 'teamcity', 'bamboo', 'octopus deploy',
            'helm', 'kustomize', 'skaffold', 'istio', 'linkerd', 'consul', 'envoy', 'istio', 'vault', 'packer',
            'vagrant', 'datadog', 'new relic', 'dynatrace', 'splunk', 'logstash', 'elasticsearch', 'kibana',
            'fluentd', 'graylog', 'zipkin', 'jaeger', 'opentelemetry', 'opentracing', 'prometheus', 'thanos',
            'cortex', 'grafana loki', 'chaos engineering', 'chaos monkey', 'chaos toolkit', 'litmus', 'chaos mesh',
            'devops', 'sre', 'site reliability engineering', 'infrastructure as code', 'iac', 'gitops',
            
            # Operating Systems
            'linux', 'unix', 'windows', 'macos', 'ios', 'android', 'ubuntu', 'debian', 'centos',
            'red hat', 'fedora', 'opensuse', 'arch linux', 'gentoo', 'alpine', 'kali', 'freebsd',
            'openbsd', 'netbsd', 'solaris', 'aix', 'bash', 'powershell', 'zsh', 'fish', 'shell',
            'cmd', 'command line', 'terminal', 'wsl', 'hyperv', 'vmware', 'virtualbox', 'qemu', 'kvm',
            
            # Version Control
            'git', 'github', 'gitlab', 'bitbucket', 'svn', 'mercurial', 'perforce', 'tfs',
            'azure repos', 'gitflow', 'trunk based', 'monorepo', 'semantic versioning', 'semver',
            'conventional commits', 'husky', 'lint-staged', 'commitlint', 'feature branch',
            
            # APIs & Services
            'rest', 'restful', 'soap', 'graphql', 'gql', 'grpc', 'api gateway', 'swagger', 'openapi',
            'api', 'apis', 'microservices', 'service mesh', 'serverless', 'webhook', 'websocket', 'sse',
            'server sent events', 'pubsub', 'mqtt', 'amqp', 'stomp', 'oauth', 'oauth2', 'jwt', 'openid',
            'openid connect', 'saml', 'soap', 'wsdl', 'hateoas', 'cors', 'api first', 'api design',
            'api documentation', 'api testing', 'postman', 'insomnia', 'pact', 'swagger', 'openapi',
            'raml', 'api blueprint', 'oauth2 proxy', 'kong', 'tyk', 'apigee', 'amazon api gateway',
            'azure api management', 'cloud endpoints', 'istio', 'envoy', 'ambassador', 'traefik',
            
            # Data Processing & Analytics
            'kafka', 'rabbitmq', 'apache spark', 'spark', 'hadoop', 'hive', 'pig', 'flink', 'nifi', 'airflow',
            'etl', 'data pipeline', 'data warehouse', 'data lake', 'big data', 'stream processing',
            'batch processing', 'real time', 'distributed systems', 'mapreduce', 'yarn', 'hdfs', 'hbase',
            'impala', 'presto', 'druid', 'storm', 'zookeeper', 'activemq', 'celery', 'zeromq', 'kafka streams',
            'ksqldb', 'debezium', 'flume', 'samza', 'kinesis', 'pubsub', 'data mesh', 'data fabric',
            'dremio', 'trino', 'alluxio', 'oozie', 'dagster', 'prefect', 'kedro', 'kubeflow', 'mlflow',
            'luigi', 'gobblin', 'pentaho', 'talend', 'informatica', 'matillion', 'fivetran', 'stitch',
            'segment', 'dbt', 'redpanda', 'pinot', 'stargate', 'jupyterhub', 'keda', 'knative', 'ray',
            'dask', 'pandas', 'numpy', 'polars', 'arrow', 'parquet', 'avro', 'orc', 'protobuf',
            'json schema', 'thrift', 'cap n proto', 'flatbuffers', 'messagepack',
            
            # Machine Learning & AI
            'machine learning', 'deep learning', 'neural networks', 'tensorflow', 'pytorch', 'keras',
            'scikit-learn', 'opencv', 'nlp', 'computer vision', 'artificial intelligence', 'ai',
            'ml', 'data science', 'natural language processing', 'transformers', 'huggingface', 'llm',
            'large language models', 'gpt', 'bert', 't5', 'llama', 'falcon', 'mistral', 'finetuning',
            'transfer learning', 'mlops', 'feature engineering', 'feature store', 'model registry',
            'model deployment', 'model monitoring', 'model explainability', 'xai', 'explainable ai',
            'model interpretability', 'data drift', 'concept drift', 'model drift', 'lstm', 'rnn',
            'cnn', 'autoencoder', 'gan', 'reinforcement learning', 'supervised learning',
            'unsupervised learning', 'semi-supervised learning', 'self-supervised learning',
            'federated learning', 'active learning', 'online learning', 'ensemble learning',
            'vector database', 'vector search', 'faiss', 'weaviate', 'pinecone', 'milvus',
            'qdrant', 'vertex ai', 'sagemaker', 'mlflow', 'kubeflow', 'seldon', 'ray', 'langchain',
            'llamaindex', 'autogluon', 'h2o', 'datarobot', 'rapidminer', 'knime', 'ludwig',
            'catboost', 'xgboost', 'lightgbm', 'numpy', 'pandas', 'scipy', 'matplotlib',
            'seaborn', 'plotly', 'dash', 'streamlit', 'gradio', 'yolov8', 'mediapipe',
            'whisper', 'stable diffusion', 'dalle', 'midjourney', 'embeddings',
            
            # Software Development Methodologies
            'agile', 'scrum', 'kanban', 'waterfall', 'xp', 'lean', 'devops', 'tdd', 'bdd',
            'extreme programming', 'safe', 'less', 'scrumban', 'crystal', 'dsdm', 'fdd',
            'rad', 'spiral', 'pair programming', 'mob programming', 'ddd', 'domain driven design',
            'cqrs', 'event sourcing', 'clean architecture', 'hexagonal architecture', 'onion architecture',
            'ports and adapters', 'vertical slice', 'mvc', 'mvvm', 'mvp', 'flux', 'redux',
            'design patterns', 'solid', 'dry', 'kiss', 'yagni', 'cohesion', 'coupling',
            'refactoring', 'code smells', 'technical debt', 'continuous improvement',
            
            # Testing
            'unit testing', 'integration testing', 'e2e testing', 'selenium', 'cypress', 'jest',
            'mocha', 'chai', 'junit', 'testng', 'pytest', 'jasmine', 'karma', 'protractor', 'puppeteer',
            'playwright', 'webdriver', 'cucumber', 'specflow', 'gherkin', 'gatling', 'jmeter',
            'locust', 'k6', 'postman', 'soapui', 'assertj', 'hamcrest', 'mockito', 'wiremock',
            'vcr', 'msw', 'nock', 'karate', 'jbehave', 'robotframework', 'appium', 'espresso',
            'xctest', 'xctestui', 'junit5', 'testcontainers', 'test pyramid', 'test quadrant',
            'tdd', 'bdd', 'atdd', 'shift left', 'mutation testing', 'property based testing',
            'chaos engineering', 'pact', 'contract testing', 'consumer driven contracts',
            'mocking', 'stubbing', 'spying', 'test double', 'test fixture', 'test harness',
            'test coverage', 'code coverage', 'branch coverage', 'line coverage', 'path coverage',
            
            # Security
            'cybersecurity', 'infosec', 'penetration testing', 'encryption', 'oauth', 'jwt',
            'authentication', 'authorization', 'iam', 'sso', 'saml', 'ldap', 'pki',
            'vulnerability scanning', 'static analysis', 'sast', 'dast', 'iast', 'rasp',
            'owasp', 'wasp top 10', 'sql injection', 'xss', 'csrf', 'idor', 'security headers',
            'content security policy', 'csp', 'cors', 'https', 'tls', 'ssl', 'vpn', 'firewall',
            'waf', 'dlp', 'intrusion detection', 'ids', 'ips', 'siem', 'soar', 'zero trust',
            'devsecops', 'threat modeling', 'stride', 'dread', 'cvss', 'cve', 'cwe', 'hipaa',
            'gdpr', 'pci dss', 'soc2', 'iso27001', 'nist', 'fedramp', 'ccpa', 'defense in depth',
            'principle of least privilege', 'mfa', '2fa', 'hardening', 'patching', 'log4j',
            'secrets management', 'vault', 'key management', 'kms', 'hsm', 'encryption at rest',
            'encryption in transit', 'end to end encryption', 'e2ee', 'pgp', 'gpg', 'aes', 'rsa',
            'ecdsa', 'x509', 'ca', 'certificate authority', 'secure sdlc', 'security champion',
            
            # Architecture Patterns
            'microservices', 'monolith', 'soa', 'event driven', 'event-driven', 'cqrs', 'ddd',
            'mvp', 'mvc', 'mvvm', 'domain driven design', 'hexagonal', 'onion', 'clean architecture',
            'vertical slice', 'serverless', 'microkernel', 'layered', 'space based', 'master slave',
            'pipes and filters', 'client server', 'peer to peer', 'broker', 'service mesh', 'repository',
            'blackboard', 'saga', 'cqrs', 'event sourcing', 'strangler fig', 'circuit breaker',
            'bulkhead', 'sidecar', 'ambassador', 'backend for frontend', 'bff', 'api gateway',
            'orchestration', 'choreography', 'outbox', 'anticorruption layer', 'dpr', 'distributed monolith',
            
            # Others
            'blockchain', 'iot', 'web3', 'augmented reality', 'virtual reality', 'ar', 'vr',
            'cloud computing', 'edge computing', 'distributed systems', 'parallel computing',
            'high performance computing', 'cryptography', 'quantum computing', 'nlp', 'sentiment analysis',
            'telemetry', 'ci / cd', 'sdlc', 'event driven architecture', '5g', 'wifi6', 'distributed ledger',
            'crypto', 'nft', 'defi', 'dao', 'smart contract', 'ethereum', 'bitcoin', 'solana', 'metaverse',
            'digital twin', 'industry 4.0', 'computer graphics', 'game development', 'unity', 'unreal engine',
            'webrtc', 'voice recognition', 'speech to text', 'text to speech', 'ocr', 'computer vision',
            'robotics', 'ros', 'drone', 'embedded systems', 'fpga', 'asic', 'gpu', 'tpu', 'raspberry pi',
            'arduino', 'bioinformatics', 'computational biology', 'fintech', 'regtech', 'insurtech',
            'biotech', 'medtech', 'healthtech', 'edtech', 'govtech', 'legaltech', 'proptech',
            'mobility', 'autonomous vehicles', 'self driving', 'last mile', 'electric vehicles',
            'sustainable tech', 'green tech', 'carbon footprint', 'renewables', 'smart city',
            'smart home', 'wearables', 'deepfake', 'synthetic media', 'synthetic data',
            'data science', 'data engineering', 'data analytics', 'business intelligence', 'bi',
            'decision intelligence', 'predictive analytics', 'prescriptive analytics',
            'descriptive analytics', 'diagnostic analytics', 'data visualization', 'data governance',
            'data quality', 'data lineage', 'data catalog', 'master data management', 'mdm',
            'customer data platform', 'cdp', 'crm', 'erp', 'cms', 'dms', 'workflow', 'bpm',
            'process mining', 'robotic process automation', 'rpa', 'low code', 'no code',
            'citizen developer', 'enterprise architecture', 'solution architecture',
            'product management', 'program management', 'project management', 'portfolio management',
            'technical writing', 'documentation', 'ui', 'ux', 'user experience', 'user interface',
            'usability', 'accessibility', 'a11y', 'i18n', 'l10n', 'internationalization',
            'localization', 'responsive design', 'mobile first', 'progressive enhancement',
            'graceful degradation', 'seo', 'sem', 'digital marketing', 'growth hacking',
            'content strategy', 'conversion optimization', 'ab testing', 'multivariate testing',
            'analytics', 'attribution', 'funnel analysis', 'cohort analysis', 'retention',
            'acquisition', 'activation', 'revenue', 'referral', 'saas', 'paas', 'iaas', 'faas',
            'baas', 'daas', 'caas', 'maas', 'on premise', 'on prem', 'hybrid cloud', 'multicloud',
            'public cloud', 'private cloud', 'community cloud', 'managed services',
            'professional services', 'service level agreement', 'sla', 'ops', 'operations',
            'sysadmin', 'systems administration', 'network administration', 'database administration',
            'dba', 'technical support', 'help desk', 'service desk', 'incident management',
            'problem management', 'change management', 'release management', 'configuration management',
            'asset management', 'capacity management', 'availability management', 'security management',
            'risk management', 'compliance', 'governance', 'itil', 'itsm', 'cobit', 'togaf',
            'zachman', 'soa', 'eai', 'esb', 'etl', 'elt', 'bi', 'olap', 'oltp', 'data mart',
            'self service bi', 'data silo', 'data democratization', 'citizen data scientist',

            # frontend specific skills
            'frontend', 'front end', 'front-end', 'ui development', 'user interface development',
            'web design', 'responsive design', 'mobile first', 'progressive enhancement',
            'motion design', 'animation', 'gsap', 'framer motion', 'lottie', 'threejs',
            'canvas', 'svg', 'webgl', 'web audio', 'web speech', 'web bluetooth',
            'web usb', 'web serial', 'web midi', 'clipboard api', 'drag and drop api',
            'geolocation api', 'pwa', 'progressive web app', 'service worker', 'web worker',
            'indexeddb', 'localstorage', 'sessionstorage', 'cache api', 'fetch api', 'promise api',
            'async await', 'es6', 'es2015', 'es2016', 'es2017', 'es2018', 'es2019', 'es2020',
            'destructuring', 'spread operator', 'arrow functions', 'closures', 'higher order functions',
            'functional programming', 'immutability', 'state management', 'client side rendering',
            'server side rendering', 'static site generation', 'jamstack', 'headless cms',
            'microfrontends', 'module federation', 'code splitting', 'tree shaking', 'hot module replacement',
            'single page application', 'spa', 'progressive web app', 'pwa', 'multi page application',
            'mpa', 'server components', 'client components', 'hydration', 'islands architecture',
            'web components', 'shadow dom', 'custom elements', 'templates', 'slots',
            
            # Backend specific skills
            'backend', 'back end', 'back-end', 'api development', 'middleware', 'serverless',
            'faas', 'function as a service', 'baas', 'backend as a service', 'rest api',
            'restful api', 'graphql api', 'grpc api', 'soap api', 'webhook', 'websocket',
            'server sent events', 'sse', 'long polling', 'short polling', 'http/2', 'http/3',
            'quic', 'tcp', 'udp', 'socket', 'domain driven design', 'ddd', 'cqrs', 'event sourcing',
            'saga pattern', 'outbox pattern', 'bulkhead pattern', 'circuit breaker pattern',
            'retry pattern', 'fallback pattern', 'timeout pattern', 'rate limiting', 'throttling',
            'batching', 'caching', 'connection pooling', 'idempotency', 'eventual consistency',
            'strong consistency', 'acid', 'base', 'cap theorem', 'sharding', 'partitioning',
            'replication', 'master slave', 'leader follower', 'peer to peer', 'consensus algorithm',
            'paxos', 'raft', 'zab', 'distributed transaction', 'two phase commit', 'three phase commit',
            'saga', 'distributed lock', 'distributed cache', 'distributed session', 'distributed tracing',
            'distributed logging', 'distributed monitoring', 'distributed config', 'service discovery',
            'service registry', 'service mesh', 'api gateway', 'load balancer', 'reverse proxy',
            'forward proxy', 'cdn', 'content delivery network', 'edge computing', 'fog computing',
            'cloud computing', 'iaas', 'paas', 'saas', 'serverless', 'faas', 'caas', 'kubernetes',
            'docker', 'container', 'virtualization', 'hypervisor', 'vm', 'virtual machine',
            'bare metal', 'on premise', 'on prem', 'hybrid cloud', 'multi cloud', 'public cloud',
            'private cloud', 'community cloud', 'distributed system', 'scalability', 'high availability',
            'fault tolerance', 'resilience', 'reliability', 'observability', 'monitoring', 'logging',
            'tracing', 'alerting', 'metrics', 'telemetry', 'apm', 'application performance monitoring',
            'profiling', 'debugging', 'testing', 'unit testing', 'integration testing', 'functional testing',
            'end to end testing', 'load testing', 'stress testing', 'chaos testing', 'penetration testing',
            'security testing', 'performance testing', 'regression testing', 'smoke testing', 'sanity testing',
            'acceptance testing', 'alpha testing', 'beta testing', 'canary testing', 'a/b testing',
            'blue green deployment', 'canary deployment', 'rolling deployment', 'recreate deployment',
            'shadow deployment', 'feature flag', 'feature toggle', 'dark launch', 'soft launch',
            'hard launch', 'rollback', 'rollout', 'deployment', 'release', 'hotfix', 'patch',
            'minor release', 'major release', 'semantic versioning', 'semver',
            
            # Mobile specific skills
            'mobile development', 'ios development', 'android development', 'react native',
            'flutter', 'xamarin', 'ionic', 'cordova', 'capacitor', 'nativescript', 'kotlin',
            'swift', 'objective c', 'java', 'dart', 'swiftui', 'uikit', 'jetpack compose',
            'android jetpack', 'material design', 'human interface guidelines', 'hig',
            'app store', 'play store', 'app store optimization', 'aso', 'push notification',
            'deep linking', 'universal link', 'app link', 'app clip', 'instant app',
            'offline first', 'responsive design', 'adaptive design', 'mobile first',
            'progressive enhancement', 'graceful degradation', 'touch interaction',
            'gesture recognition', 'biometric authentication', 'face id', 'touch id',
            'fingerprint authentication', 'location services', 'geofencing', 'beacon',
            'bluetooth', 'nfc', 'near field communication', 'arkit', 'arcore', 'augmented reality',
            'virtual reality', 'vr', 'ar', 'mixed reality', 'mr', 'extended reality', 'xr',
            'camera api', 'photo api', 'video api', 'audio api', 'speech recognition',
            'voice recognition', 'text to speech', 'speech to text', 'natural language processing',
            'nlp', 'machine learning', 'ml', 'deep learning', 'artificial intelligence', 'ai',
            'core ml', 'tensorflow lite', 'ml kit', 'firebase ml', 'on device ml', 'edge ml',
            'firebase', 'amplitude', 'mixpanel', 'appcenter', 'crashlytics', 'analytics',
            'user engagement', 'retention', 'acquisition', 'activation', 'revenue', 'referral',
            'app monetization', 'in app purchase', 'subscription', 'freemium', 'ad based',
            'hybrid monetization', 'app security', 'app privacy', 'app accessibility', 'a11y',
            'internationalization', 'i18n', 'localization', 'l10n', 'right to left', 'rtl',
            'left to right', 'ltr', 'multi language', 'multi region', 'multi currency',
            'multi timezone', 'multi calendar', 'multi script', 'multi culture', 'testing',
            'unit testing', 'integration testing', 'ui testing', 'screenshot testing',
            'performance testing', 'memory leak detection', 'battery usage optimization',
            'network usage optimization', 'storage usage optimization', 'cpu usage optimization',
            'gpu usage optimization', 'ram usage optimization', 'app size optimization',
            'code obfuscation', 'code signing', 'provisioning profile', 'certificate',
            'keystore', 'build automation', 'continuous integration', 'continuous delivery',
            'continuous deployment', 'ci/cd',
            
            # Data Science specific skills
            'data science', 'machine learning', 'deep learning', 'artificial intelligence',
            'neural networks', 'natural language processing', 'computer vision', 'reinforcement learning',
            'supervised learning', 'unsupervised learning', 'semi supervised learning',
            'self supervised learning', 'transfer learning', 'meta learning', 'few shot learning',
            'zero shot learning', 'one shot learning', 'active learning', 'online learning',
            'offline learning', 'batch learning', 'ensemble learning', 'federated learning',
            'distributed learning', 'quantum machine learning', 'explainable ai', 'xai',
            'interpretable machine learning', 'fairness in machine learning', 'bias in machine learning',
            'ethics in ai', 'responsible ai', 'data mining', 'data analysis', 'data visualization',
            'data storytelling', 'descriptive analytics', 'diagnostic analytics', 'predictive analytics',
            'prescriptive analytics', 'statistical analysis', 'statistical modeling', 'statistical inference',
            'hypothesis testing', 'a/b testing', 'multivariate testing', 'regression analysis',
            'classification', 'clustering', 'dimensionality reduction', 'feature engineering',
            'feature selection', 'feature extraction', 'feature transformation', 'feature scaling',
            'feature normalization', 'feature encoding', 'feature hashing', 'feature crossing',
            'feature store', 'experiment tracking', 'model registry', 'model versioning',
            'model deployment', 'model serving', 'model monitoring', 'model retraining',
            'model evaluation', 'model validation', 'model calibration', 'model compression',
            'model quantization', 'model pruning', 'model distillation', 'model fine tuning',
            'hyperparameter optimization', 'hyperparameter tuning', 'grid search', 'random search',
            'bayesian optimization', 'evolutionary algorithms', 'genetic algorithms',
            'particle swarm optimization', 'simulated annealing', 'reinforcement learning',
            'q learning', 'deep q learning', 'policy gradient', 'actor critic', 'monte carlo tree search',
            'mcts', 'alpha beta pruning', 'minimax', 'game theory', 'decision theory',
            'utility theory', 'probability theory', 'bayesian statistics', 'frequentist statistics',
            'parametric statistics', 'nonparametric statistics', 'inferential statistics',
            'descriptive statistics', 'causal inference', 'correlation', 'causation',
            'confounding variable', 'selection bias', 'survivorship bias',
            'sampling bias', 'confirmation bias', 'hindsight bias', 'overfitting', 'underfitting',
            'bias variance tradeoff', 'regularization', 'dropout', 'batch normalization',
            'layer normalization', 'instance normalization', 'group normalization',
            'weight normalization', 'spectral normalization', 'data augmentation',
            'synthetic data generation', 'generative adversarial networks', 'gan',
            'variational autoencoder', 'vae', 'diffusion models', 'flow based models',
            'autoregressive models', 'transformer models', 'attention mechanism',
            'self attention', 'multi head attention', 'cross attention', 'positional encoding',
            'embeddings', 'word embeddings', 'word2vec', 'glove', 'fasttext', 'elmo',
            'bert', 'gpt', 't5', 'llama', 'mistral', 'gemma', 'claude', 'palm', 'phi',
            'stable diffusion', 'midjourney', 'dalle', 'imagen', 'neural style transfer',
            'image super resolution', 'image segmentation', 'object detection',
            'instance segmentation', 'semantic segmentation', 'panoptic segmentation',
            'pose estimation', 'facial recognition', 'gesture recognition', 'speech recognition',
            'speech synthesis', 'speaker verification', 'speaker identification',
            'sound classification', 'audio classification', 'music generation',
            'recommendation systems', 'collaborative filtering', 'content based filtering',
            'hybrid recommendation', 'matrix factorization', 'singular value decomposition',
            'principal component analysis', 'pca', 'linear discriminant analysis', 'lda',
            't sne', 'umap', 'isomap', 'mds', 'time series analysis', 'time series forecasting',
            'anomaly detection', 'outlier detection', 'fraud detection', 'network analysis',
            'graph analysis', 'graph neural networks', 'knowledge graphs', 'ontology',
            'taxonomy', 'information retrieval', 'search engines', 'ranking algorithms',
            'pagerank', 'textrank', 'tfidf', 'bm25', 'ltr', 'learning to rank',
            'data engineering', 'data architecture', 'data modeling', 'data warehousing',
            'data lake', 'data lakehouse', 'data mesh', 'data fabric', 'data governance',
            'data quality', 'data lineage', 'data observability', 'data catalog',
            'data discovery', 'data classification', 'data security', 'data privacy',
            'data ethics', 'data pipeline', 'etl', 'extract transform load', 'elt',
            'extract load transform', 'data integration', 'data replication', 'data migration',
            'change data capture', 'cdc', 'data streaming', 'batch processing',
            'real time processing', 'near real time processing', 'stream processing',
            'event streaming', 'event processing', 'complex event processing',
            'event driven architecture', 'pub sub', 'publish subscribe', 'message broker',
            'message queue', 'distributed messaging', 'change data capture',
            'lambda architecture', 'kappa architecture', 'data vault', 'dimensional modeling',
            'star schema', 'snowflake schema', 'fact table', 'dimension table',
            'slowly changing dimension', 'scd', 'oltp', 'olap', 'htap', 'big data',
            'hadoop', 'spark', 'flink', 'kafka', 'druid', 'airflow', 'prefect',
            'dagster', 'luigi', 'nifi', 'kedro', 'mlflow', 'kubeflow', 'metaflow',
            'dvc', 'great expectations', 'dbt', 'looker', 'tableau', 'power bi',
            'qlik', 'superset', 'redash', 'mode', 'plotly', 'dash', 'streamlit',
            'gradio', 'panel', 'bokeh', 'matplotlib', 'seaborn', 'd3', 'ggplot',
            'r', 'r studio', 'python', 'sql', 'julia', 'scala', 'java', 'numpy',
            'pandas', 'polars', 'dask', 'vaex', 'modin', 'cudf', 'scipy', 'statsmodels',
            'scikit learn', 'tensorflow', 'pytorch', 'keras', 'jax', 'mxnet', 'xgboost',
            'lightgbm', 'catboost', 'h2o', 'prophet', 'gensim', 'spacy', 'nltk',
            'huggingface', 'transformers', 'datasets', 'tokenizers', 'diffusers',
            'opencv', 'pillow', 'scikit image', 'librosa', 'speechbrain', 'networkx',
            'stellargraph', 'pyg', 'dgl', 'langchain', 'llamaindex', 'haystack',
            'feast', 'tecton', 'hopsworks', 'arize', 'fiddler', 'whylabs', 'evidently',
            'seldon', 'bentoml', 'triton', 'torchserve', 'tensorflow serving',
            'sagemaker', 'vertex ai', 'azure ml', 'databricks', 'snowflake', 'bigquery',
            'redshift', 'synapse', 'athena', 'firebolt', 'clickhouse', 'pinot',
            'druid', 'elasticsearch', 'opensearch', 'mongo', 'cassandra', 'neo4j',
            'neptune', 'tigergraph', 'redis', 'memcached', 'weaviate', 'pinecone',
            'milvus', 'qdrant', 'chroma', 'faiss', 'annoy', 'hnsw', 'vector database',
            'vector search', 'neural search', 'semantic search', 'conversational search',
            'conversational ai', 'chatbot', 'voicebot', 'dialog system', 'question answering',
            'text summarization', 'text classification', 'sentiment analysis',
            'named entity recognition', 'ner', 'part of speech tagging', 'pos',
            'dependency parsing', 'constituency parsing', 'coreference resolution',
            'relationship extraction', 'machine translation', 'text generation',
            'text to image', 'image to text', 'image captioning', 'visual question answering',
            'vqa', 'multimodal learning', 'cross modal retrieval', 'zero shot learning',
            'few shot learning', 'one shot learning', 'prompt engineering', 'in context learning',
            'chain of thought', 'retrieval augmented generation', 'rag', 'llm',
            'large language model', 'foundation model', 'pretrained model',
            'fine tuning', 'parameter efficient fine tuning', 'peft', 'lora',
            'qlora', 'adapter', 'prefix tuning', 'prompt tuning', 'instruction tuning',
            'rlhf', 'reinforcement learning from human feedback', 'alignment',
            'constitutional ai', 'red teaming', 'adversarial testing', 'jailbreaking',
            'prompt injection', 'data poisoning', 'model stealing', 'model inversion',
            'membership inference', 'differential privacy', 'federated learning',
            'model distillation', 'model compression', 'model quantization', 'model pruning',
            'knowledge distillation', 'model merging', 'model ensemble', 'ensemble learning',
            'bagging', 'boosting', 'stacking', 'random forest', 'gradient boosting',
            'adaboost', 'xgboost', 'lightgbm', 'catboost', 'decision tree',
            'logistic regression', 'linear regression', 'ridge regression',
            'lasso regression', 'elastic net', 'support vector machine', 'svm',
            'naive bayes', 'k nearest neighbors', 'knn', 'k means', 'dbscan',
            'hierarchical clustering', 'gmm', 'gaussian mixture model', 'hidden markov model',
            'hmm', 'conditional random field', 'crf', 'markov random field', 'mrf',
            'bayesian network', 'graphical model', 'causal inference', 'do calculus',
            'instrumental variable', 'propensity score matching', 'difference in differences',
            'regression discontinuity', 'randomized controlled trial', 'rct', 'ab testing',
            'multi armed bandit', 'thompson sampling', 'ucb', 'upper confidence bound'
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
        file_type (str, optional): Type of resume file ('pdf' or 'docx' or 'doc'). Defaults to "pdf".
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

