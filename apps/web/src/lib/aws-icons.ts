/**
 * AWS Icons Configuration
 * 
 * This module provides a centralized way to manage AWS icon paths.
 * When AWS releases new icon sets, only update the VERSION constant below.
 * 
 * AWS Icon Release History:
 * - 07/31/2025: Current version
 * 
 * To update to a new version:
 * 1. Download the new icon set from AWS Architecture Icons page
 * 2. Place it in /public/aws-icons/
 * 3. Update the VERSION constant below
 * 4. Optionally: Keep old version for rollback capability
 */

// ============================================
// CONFIGURATION - Update this when AWS releases new icons
// ============================================
const AWS_ICONS_VERSION = '07312025';

// Base path for the icon package
const ICON_PACKAGE_PATH = `/aws-icons/Asset-Package_${AWS_ICONS_VERSION}`;

// Base paths for different icon types
const ICON_PATHS = {
  architecture: `${ICON_PACKAGE_PATH}/Architecture-Service-Icons`,
  resource: `${ICON_PACKAGE_PATH}/Resource-Icons`,
  category: `${ICON_PACKAGE_PATH}/Category-Icons`,
  group: `${ICON_PACKAGE_PATH}/Architecture-Group-Icons`,
} as const;

// ============================================
// ICON PATH BUILDERS
// ============================================

/**
 * Get architecture icon path
 * @param category - Icon category (e.g., 'Arch_Database', 'Arch_Compute')
 * @param size - Icon size (16, 32, 48, or 64)
 * @param filename - Icon filename
 * @returns Full path to the icon
 */
export function getArchitectureIcon(
  category: string,
  size: 16 | 32 | 48 | 64,
  filename: string
): string {
  return `${ICON_PATHS.architecture}/${category}/${size}/${filename}`;
}

/**
 * Get resource icon path
 * @param category - Icon category (e.g., 'Res_Database', 'Res_General-Icons')
 * @param folder - Subfolder (e.g., 'Res_48_Light')
 * @param filename - Icon filename
 * @returns Full path to the icon
 */
export function getResourceIcon(
  category: string,
  folder: string,
  filename: string
): string {
  return `${ICON_PATHS.resource}/${category}/${folder}/${filename}`;
}

/**
 * Get category icon path
 * @param size - Icon size (16, 32, 48, or 64)
 * @param filename - Icon filename
 * @returns Full path to the icon
 */
export function getCategoryIcon(
  size: 16 | 32 | 48 | 64,
  filename: string
): string {
  return `${ICON_PATHS.category}/Arch-Category_${size}/${filename}`;
}

/**
 * Get group icon path
 * @param filename - Icon filename
 * @returns Full path to the icon
 */
export function getGroupIcon(filename: string): string {
  return `${ICON_PATHS.group}/${filename}`;
}

// ============================================
// COMPLETE SERVICE ICON MAP (307 services)
// ============================================

/**
 * Complete mapping of AWS service keywords to their icon paths.
 * Format: [category, filename]
 * 
 * This map covers ALL 307 AWS architecture service icons.
 */
const SERVICE_ICON_MAP: Record<string, [string, string]> = {
  // ============================================
  // ANALYTICS (20 services)
  // ============================================
  'clean rooms': ['Arch_Analytics', 'Arch_AWS-Clean-Rooms_64.svg'],
  'data exchange': ['Arch_Analytics', 'Arch_AWS-Data-Exchange_64.svg'],
  'entity resolution': ['Arch_Analytics', 'Arch_AWS-Entity-Resolution_64.svg'],
  'glue databrew': ['Arch_Analytics', 'Arch_AWS-Glue-DataBrew_64.svg'],
  'databrew': ['Arch_Analytics', 'Arch_AWS-Glue-DataBrew_64.svg'],
  'glue': ['Arch_Analytics', 'Arch_AWS-Glue_64.svg'],
  'lake formation': ['Arch_Analytics', 'Arch_AWS-Lake-Formation_64.svg'],
  'athena': ['Arch_Analytics', 'Arch_Amazon-Athena_64.svg'],
  'cloudsearch': ['Arch_Analytics', 'Arch_Amazon-CloudSearch_64.svg'],
  'data firehose': ['Arch_Analytics', 'Arch_Amazon-Data-Firehose_64.svg'],
  'firehose': ['Arch_Analytics', 'Arch_Amazon-Data-Firehose_64.svg'],
  'datazone': ['Arch_Analytics', 'Arch_Amazon-DataZone_64.svg'],
  'emr': ['Arch_Analytics', 'Arch_Amazon-EMR_64.svg'],
  'elastic mapreduce': ['Arch_Analytics', 'Arch_Amazon-EMR_64.svg'],
  'finspace': ['Arch_Analytics', 'Arch_Amazon-FinSpace_64.svg'],
  'kinesis data streams': ['Arch_Analytics', 'Arch_Amazon-Kinesis-Data-Streams_64.svg'],
  'kinesis video': ['Arch_Analytics', 'Arch_Amazon-Kinesis-Video-Streams_64.svg'],
  'kinesis': ['Arch_Analytics', 'Arch_Amazon-Kinesis_64.svg'],
  'managed flink': ['Arch_Analytics', 'Arch_Amazon-Managed-Service-for-Apache-Flink_64.svg'],
  'apache flink': ['Arch_Analytics', 'Arch_Amazon-Managed-Service-for-Apache-Flink_64.svg'],
  'msk': ['Arch_Analytics', 'Arch_Amazon-Managed-Streaming-for-Apache-Kafka_64.svg'],
  'kafka': ['Arch_Analytics', 'Arch_Amazon-Managed-Streaming-for-Apache-Kafka_64.svg'],
  'opensearch': ['Arch_Analytics', 'Arch_Amazon-OpenSearch-Service_64.svg'],
  'elasticsearch': ['Arch_Analytics', 'Arch_Amazon-OpenSearch-Service_64.svg'],
  'quicksight': ['Arch_Analytics', 'Arch_Amazon-QuickSight_64.svg'],
  'redshift': ['Arch_Analytics', 'Arch_Amazon-Redshift_64.svg'],

  // ============================================
  // APP INTEGRATION (10 services)
  // ============================================
  'appsync': ['Arch_App-Integration', 'Arch_AWS-AppSync_64.svg'],
  'app sync': ['Arch_App-Integration', 'Arch_AWS-AppSync_64.svg'],
  'b2b data interchange': ['Arch_App-Integration', 'Arch_AWS-B2B-Data-Interchange_64.svg'],
  'express workflows': ['Arch_App-Integration', 'Arch_AWS-Express-Workflows_64.svg'],
  'step functions': ['Arch_App-Integration', 'Arch_AWS-Step-Functions_64.svg'],
  'stepfunctions': ['Arch_App-Integration', 'Arch_AWS-Step-Functions_64.svg'],
  'appflow': ['Arch_App-Integration', 'Arch_Amazon-AppFlow_64.svg'],
  'eventbridge': ['Arch_App-Integration', 'Arch_Amazon-EventBridge_64.svg'],
  'event bridge': ['Arch_App-Integration', 'Arch_Amazon-EventBridge_64.svg'],
  'amazon mq': ['Arch_App-Integration', 'Arch_Amazon-MQ_64.svg'],
  'activemq': ['Arch_App-Integration', 'Arch_Amazon-MQ_64.svg'],
  'rabbitmq': ['Arch_App-Integration', 'Arch_Amazon-MQ_64.svg'],
  'mwaa': ['Arch_App-Integration', 'Arch_Amazon-Managed-Workflows-for-Apache-Airflow_64.svg'],
  'airflow': ['Arch_App-Integration', 'Arch_Amazon-Managed-Workflows-for-Apache-Airflow_64.svg'],
  'sns': ['Arch_App-Integration', 'Arch_Amazon-Simple-Notification-Service_64.svg'],
  'simple notification': ['Arch_App-Integration', 'Arch_Amazon-Simple-Notification-Service_64.svg'],
  'sqs': ['Arch_App-Integration', 'Arch_Amazon-Simple-Queue-Service_64.svg'],
  'simple queue': ['Arch_App-Integration', 'Arch_Amazon-Simple-Queue-Service_64.svg'],

  // ============================================
  // ARTIFICIAL INTELLIGENCE / ML (42 services)
  // ============================================
  'app studio': ['Arch_Artificial-Intelligence', 'Arch_AWS-App-Studio_64.svg'],
  'deep learning ami': ['Arch_Artificial-Intelligence', 'Arch_AWS-Deep-Learning-AMIs_64.svg'],
  'deep learning container': ['Arch_Artificial-Intelligence', 'Arch_AWS-Deep-Learning-Containers_64.svg'],
  'deepcomposer': ['Arch_Artificial-Intelligence', 'Arch_AWS-DeepComposer_64.svg'],
  'deepracer': ['Arch_Artificial-Intelligence', 'Arch_AWS-DeepRacer_64.svg'],
  'healthimaging': ['Arch_Artificial-Intelligence', 'Arch_AWS-HealthImaging_64.svg'],
  'healthlake': ['Arch_Artificial-Intelligence', 'Arch_AWS-HealthLake_64.svg'],
  'healthomics': ['Arch_Artificial-Intelligence', 'Arch_AWS-HealthOmics_64.svg'],
  'healthscribe': ['Arch_Artificial-Intelligence', 'Arch_AWS-HealthScribe_64.svg'],
  'neuron': ['Arch_Artificial-Intelligence', 'Arch_AWS-Neuron_64.svg'],
  'panorama': ['Arch_Artificial-Intelligence', 'Arch_AWS-Panorama_64.svg'],
  'augmented ai': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Augmented-AI-A2I_64.svg'],
  'a2i': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Augmented-AI-A2I_64.svg'],
  'bedrock': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Bedrock_64.svg'],
  'bedrock agentcore': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Bedrock_64.svg'],
  'bedrock data automation': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Bedrock_64.svg'],
  'bedrock knowledge base': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Bedrock_64.svg'],
  'agentcore': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Bedrock_64.svg'],
  'bda': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Bedrock_64.svg'],
  'codeguru': ['Arch_Artificial-Intelligence', 'Arch_Amazon-CodeGuru_64.svg'],
  'code guru': ['Arch_Artificial-Intelligence', 'Arch_Amazon-CodeGuru_64.svg'],
  'codewhisperer': ['Arch_Artificial-Intelligence', 'Arch_Amazon-CodeWhisperer_64.svg'],
  'code whisperer': ['Arch_Artificial-Intelligence', 'Arch_Amazon-CodeWhisperer_64.svg'],
  'comprehend medical': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Comprehend-Medical_64.svg'],
  'comprehend': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Comprehend_64.svg'],
  'devops guru': ['Arch_Artificial-Intelligence', 'Arch_Amazon-DevOps-Guru_64.svg'],
  'elastic inference': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Elastic-Inference_64.svg'],
  'forecast': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Forecast_64.svg'],
  'fraud detector': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Fraud-Detector_64.svg'],
  'kendra': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Kendra_64.svg'],
  'lex': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Lex_64.svg'],
  'lookout for equipment': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Lookout-for-Equipment_64.svg'],
  'lookout for metrics': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Lookout-for-Metrics_64.svg'],
  'lookout for vision': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Lookout-for-Vision_64.svg'],
  'monitron': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Monitron_64.svg'],
  'nova': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Nova_64.svg'],
  'personalize': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Personalize_64.svg'],
  'polly': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Polly_64.svg'],
  'amazon q': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Q_64.svg'],
  'rekognition': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Rekognition_64.svg'],
  'sagemaker': ['Arch_Artificial-Intelligence', 'Arch_Amazon-SageMaker-AI_64.svg'],
  'sage maker': ['Arch_Artificial-Intelligence', 'Arch_Amazon-SageMaker-AI_64.svg'],
  'ground truth': ['Arch_Artificial-Intelligence', 'Arch_Amazon-SageMaker-Ground-Truth_64.svg'],
  'studio lab': ['Arch_Artificial-Intelligence', 'Arch_Amazon-SageMaker-Studio-Lab_64.svg'],
  'textract': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Textract_64.svg'],
  'transcribe': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Transcribe_64.svg'],
  'translate': ['Arch_Artificial-Intelligence', 'Arch_Amazon-Translate_64.svg'],
  'mxnet': ['Arch_Artificial-Intelligence', 'Arch_Apache-MXNet-on-AWS_64.svg'],
  'pytorch': ['Arch_Artificial-Intelligence', 'Arch_PyTorch-on-AWS_64.svg'],
  'tensorflow': ['Arch_Artificial-Intelligence', 'Arch_TensorFlow-on-AWS_64.svg'],

  // ============================================
  // BLOCKCHAIN (2 services)
  // ============================================
  'managed blockchain': ['Arch_Blockchain', 'Arch_Amazon-Managed-Blockchain_64.svg'],
  'blockchain': ['Arch_Blockchain', 'Arch_Amazon-Managed-Blockchain_64.svg'],
  'qldb': ['Arch_Blockchain', 'Arch_Amazon-Quantum-Ledger-Database_64.svg'],
  'quantum ledger': ['Arch_Blockchain', 'Arch_Amazon-Quantum-Ledger-Database_64.svg'],

  // ============================================
  // BUSINESS APPLICATIONS (14 services)
  // ============================================
  'appfabric': ['Arch_Business-Applications', 'Arch_AWS-AppFabric_64.svg'],
  'end user messaging': ['Arch_Business-Applications', 'Arch_AWS-End-User-Messaging_64.svg'],
  'supply chain': ['Arch_Business-Applications', 'Arch_AWS-Supply-Chain_64.svg'],
  'wickr': ['Arch_Business-Applications', 'Arch_AWS-Wickr_64.svg'],
  'alexa for business': ['Arch_Business-Applications', 'Arch_Alexa-For-Business_64.svg'],
  'alexa': ['Arch_Business-Applications', 'Arch_Alexa-For-Business_64.svg'],
  'chime sdk': ['Arch_Business-Applications', 'Arch_Amazon-Chime-SDK_64.svg'],
  'chime': ['Arch_Business-Applications', 'Arch_Amazon-Chime_64.svg'],
  'connect': ['Arch_Business-Applications', 'Arch_Amazon-Connect_64.svg'],
  'pinpoint api': ['Arch_Business-Applications', 'Arch_Amazon-Pinpoint-APIs_64.svg'],
  'pinpoint': ['Arch_Business-Applications', 'Arch_Amazon-Pinpoint_64.svg'],
  'ses': ['Arch_Business-Applications', 'Arch_Amazon-Simple-Email-Service_64.svg'],
  'simple email': ['Arch_Business-Applications', 'Arch_Amazon-Simple-Email-Service_64.svg'],
  'workdocs sdk': ['Arch_Business-Applications', 'Arch_Amazon-WorkDocs-SDK_64.svg'],
  'workdocs': ['Arch_Business-Applications', 'Arch_Amazon-WorkDocs_64.svg'],
  'workmail': ['Arch_Business-Applications', 'Arch_Amazon-WorkMail_64.svg'],

  // ============================================
  // CLOUD FINANCIAL MANAGEMENT (6 services)
  // ============================================
  'billing conductor': ['Arch_Cloud-Financial-Management', 'Arch_AWS-Billing-Conductor_64.svg'],
  'budgets': ['Arch_Cloud-Financial-Management', 'Arch_AWS-Budgets_64.svg'],
  'cost explorer': ['Arch_Cloud-Financial-Management', 'Arch_AWS-Cost-Explorer_64.svg'],
  'cost and usage': ['Arch_Cloud-Financial-Management', 'Arch_AWS-Cost-and-Usage-Report_64.svg'],
  'reserved instance': ['Arch_Cloud-Financial-Management', 'Arch_Reserved-Instance-Reporting_64.svg'],
  'savings plans': ['Arch_Cloud-Financial-Management', 'Arch_Savings-Plans_64.svg'],

  // ============================================
  // COMPUTE (23 services)
  // ============================================
  'app runner': ['Arch_Compute', 'Arch_AWS-App-Runner_64.svg'],
  'batch': ['Arch_Compute', 'Arch_AWS-Batch_64.svg'],
  'compute optimizer': ['Arch_Compute', 'Arch_AWS-Compute-Optimizer_64.svg'],
  'elastic beanstalk': ['Arch_Compute', 'Arch_AWS-Elastic-Beanstalk_64.svg'],
  'beanstalk': ['Arch_Compute', 'Arch_AWS-Elastic-Beanstalk_64.svg'],
  'lambda': ['Arch_Compute', 'Arch_AWS-Lambda_64.svg'],
  'local zones': ['Arch_Compute', 'Arch_AWS-Local-Zones_64.svg'],
  'nitro enclaves': ['Arch_Compute', 'Arch_AWS-Nitro-Enclaves_64.svg'],
  'nitro': ['Arch_Compute', 'Arch_AWS-Nitro-Enclaves_64.svg'],
  'outposts family': ['Arch_Compute', 'Arch_AWS-Outposts-family_64.svg'],
  'outposts rack': ['Arch_Compute', 'Arch_AWS-Outposts-rack_64.svg'],
  'outposts server': ['Arch_Compute', 'Arch_AWS-Outposts-servers_64.svg'],
  'outposts': ['Arch_Compute', 'Arch_AWS-Outposts-family_64.svg'],
  'parallel cluster': ['Arch_Compute', 'Arch_AWS-Parallel-Cluster_64.svg'],
  'parallel computing': ['Arch_Compute', 'Arch_AWS-Parallel-Computing-Service_64.svg'],
  'serverless application repository': ['Arch_Compute', 'Arch_AWS-Serverless-Application-Repository_64.svg'],
  'sar': ['Arch_Compute', 'Arch_AWS-Serverless-Application-Repository_64.svg'],
  'simspace weaver': ['Arch_Compute', 'Arch_AWS-SimSpace-Weaver_64.svg'],
  'wavelength': ['Arch_Compute', 'Arch_AWS-Wavelength_64.svg'],
  'dcv': ['Arch_Compute', 'Arch_Amazon-DCV_64.svg'],
  'ec2 auto scaling': ['Arch_Compute', 'Arch_Amazon-EC2-Auto-Scaling_64.svg'],
  'auto scaling': ['Arch_Compute', 'Arch_Amazon-EC2-Auto-Scaling_64.svg'],
  'image builder': ['Arch_Compute', 'Arch_Amazon-EC2-Image-Builder_64.svg'],
  'ec2': ['Arch_Compute', 'Arch_Amazon-EC2_64.svg'],
  'elastic vmware': ['Arch_Compute', 'Arch_Amazon-Elastic-VMware-Service_64.svg'],
  'vmware': ['Arch_Compute', 'Arch_Amazon-Elastic-VMware-Service_64.svg'],
  'lightsail research': ['Arch_Compute', 'Arch_Amazon-Lightsail-for-Research_64.svg'],
  'lightsail': ['Arch_Compute', 'Arch_Amazon-Lightsail_64.svg'],
  'bottlerocket': ['Arch_Compute', 'Arch_Bottlerocket_64.svg'],
  'elastic fabric adapter': ['Arch_Compute', 'Arch_Elastic-Fabric-Adapter_64.svg'],
  'efa': ['Arch_Compute', 'Arch_Elastic-Fabric-Adapter_64.svg'],
  'nice enginframe': ['Arch_Compute', 'Arch_NICE-EnginFrame_64.svg'],

  // ============================================
  // CONTAINERS (9 services)
  // ============================================
  'fargate': ['Arch_Containers', 'Arch_AWS-Fargate_64.svg'],
  'ecs anywhere': ['Arch_Containers', 'Arch_Amazon-ECS-Anywhere_64.svg'],
  'eks anywhere': ['Arch_Containers', 'Arch_Amazon-EKS-Anywhere_64.svg'],
  'eks cloud': ['Arch_Containers', 'Arch_Amazon-EKS-Cloud_64.svg'],
  'eks distro': ['Arch_Containers', 'Arch_Amazon-EKS-Distro_64.svg'],
  'ecr': ['Arch_Containers', 'Arch_Amazon-Elastic-Container-Registry_64.svg'],
  'container registry': ['Arch_Containers', 'Arch_Amazon-Elastic-Container-Registry_64.svg'],
  'ecs': ['Arch_Containers', 'Arch_Amazon-Elastic-Container-Service_64.svg'],
  'elastic container service': ['Arch_Containers', 'Arch_Amazon-Elastic-Container-Service_64.svg'],
  'eks': ['Arch_Containers', 'Arch_Amazon-Elastic-Kubernetes-Service_64.svg'],
  'kubernetes': ['Arch_Containers', 'Arch_Amazon-Elastic-Kubernetes-Service_64.svg'],
  'openshift': ['Arch_Containers', 'Arch_Red-Hat-OpenShift-Service-on-AWS_64.svg'],

  // ============================================
  // CUSTOMER ENABLEMENT (8 services)
  // ============================================
  'activate': ['Arch_Customer-Enablement', 'Arch_AWS-Activate_64.svg'],
  'iq': ['Arch_Customer-Enablement', 'Arch_AWS-IQ_64.svg'],
  'managed services': ['Arch_Customer-Enablement', 'Arch_AWS-Managed-Services_64.svg'],
  'professional services': ['Arch_Customer-Enablement', 'Arch_AWS-Professional-Services_64.svg'],
  'support': ['Arch_Customer-Enablement', 'Arch_AWS-Support_64.svg'],
  'training certification': ['Arch_Customer-Enablement', 'Arch_AWS-Training-Certification_64.svg'],
  'repost private': ['Arch_Customer-Enablement', 'Arch_AWS-rePost-Private_64.svg'],
  'repost': ['Arch_Customer-Enablement', 'Arch_AWS-rePost_64.svg'],

  // ============================================
  // DATABASE (11 services)
  // ============================================
  'dms': ['Arch_Database', 'Arch_AWS-Database-Migration-Service_64.svg'],
  'database migration': ['Arch_Database', 'Arch_AWS-Database-Migration-Service_64.svg'],
  'aurora': ['Arch_Database', 'Arch_Amazon-Aurora_64.svg'],
  'aurora serverless': ['Arch_Database', 'Arch_Amazon-Aurora_64.svg'],
  'documentdb': ['Arch_Database', 'Arch_Amazon-DocumentDB_64.svg'],
  'document db': ['Arch_Database', 'Arch_Amazon-DocumentDB_64.svg'],
  'mongo': ['Arch_Database', 'Arch_Amazon-DocumentDB_64.svg'],
  'mongodb': ['Arch_Database', 'Arch_Amazon-DocumentDB_64.svg'],
  'dynamodb': ['Arch_Database', 'Arch_Amazon-DynamoDB_64.svg'],
  'dynamo': ['Arch_Database', 'Arch_Amazon-DynamoDB_64.svg'],
  'elasticache': ['Arch_Database', 'Arch_Amazon-ElastiCache_64.svg'],
  'redis': ['Arch_Database', 'Arch_Amazon-ElastiCache_64.svg'],
  'memcached': ['Arch_Database', 'Arch_Amazon-ElastiCache_64.svg'],
  'keyspaces': ['Arch_Database', 'Arch_Amazon-Keyspaces_64.svg'],
  'cassandra': ['Arch_Database', 'Arch_Amazon-Keyspaces_64.svg'],
  'memorydb': ['Arch_Database', 'Arch_Amazon-MemoryDB_64.svg'],
  'memory db': ['Arch_Database', 'Arch_Amazon-MemoryDB_64.svg'],
  'neptune': ['Arch_Database', 'Arch_Amazon-Neptune_64.svg'],
  'rds': ['Arch_Database', 'Arch_Amazon-RDS_64.svg'],
  'postgres': ['Arch_Database', 'Arch_Amazon-RDS_64.svg'],
  'postgresql': ['Arch_Database', 'Arch_Amazon-RDS_64.svg'],
  'mysql': ['Arch_Database', 'Arch_Amazon-RDS_64.svg'],
  'mariadb': ['Arch_Database', 'Arch_Amazon-RDS_64.svg'],
  'oracle': ['Arch_Database', 'Arch_Amazon-RDS_64.svg'],
  'sqlserver': ['Arch_Database', 'Arch_Amazon-RDS_64.svg'],
  'sql server': ['Arch_Database', 'Arch_Amazon-RDS_64.svg'],
  'timestream': ['Arch_Database', 'Arch_Amazon-Timestream_64.svg'],
  'oracle database at aws': ['Arch_Database', 'Arch_Oracle-Database-at-AWS_64.svg'],

  // ============================================
  // DEVELOPER TOOLS (16 services)
  // ============================================
  'cloud control api': ['Arch_Developer-Tools', 'Arch_AWS-Cloud-Control-API_64.svg'],
  'cdk': ['Arch_Developer-Tools', 'Arch_AWS-Cloud-Development-Kit_64.svg'],
  'cloud development kit': ['Arch_Developer-Tools', 'Arch_AWS-Cloud-Development-Kit_64.svg'],
  'cloud9': ['Arch_Developer-Tools', 'Arch_AWS-Cloud9_64.svg'],
  'cloudshell': ['Arch_Developer-Tools', 'Arch_AWS-CloudShell_64.svg'],
  'cloud shell': ['Arch_Developer-Tools', 'Arch_AWS-CloudShell_64.svg'],
  'codeartifact': ['Arch_Developer-Tools', 'Arch_AWS-CodeArtifact_64.svg'],
  'code artifact': ['Arch_Developer-Tools', 'Arch_AWS-CodeArtifact_64.svg'],
  'codebuild': ['Arch_Developer-Tools', 'Arch_AWS-CodeBuild_64.svg'],
  'code build': ['Arch_Developer-Tools', 'Arch_AWS-CodeBuild_64.svg'],
  'codecommit': ['Arch_Developer-Tools', 'Arch_AWS-CodeCommit_64.svg'],
  'code commit': ['Arch_Developer-Tools', 'Arch_AWS-CodeCommit_64.svg'],
  'codedeploy': ['Arch_Developer-Tools', 'Arch_AWS-CodeDeploy_64.svg'],
  'code deploy': ['Arch_Developer-Tools', 'Arch_AWS-CodeDeploy_64.svg'],
  'codepipeline': ['Arch_Developer-Tools', 'Arch_AWS-CodePipeline_64.svg'],
  'code pipeline': ['Arch_Developer-Tools', 'Arch_AWS-CodePipeline_64.svg'],
  'pipeline': ['Arch_Developer-Tools', 'Arch_AWS-CodePipeline_64.svg'],
  'cli': ['Arch_Developer-Tools', 'Arch_AWS-Command-Line-Interface_64.svg'],
  'command line': ['Arch_Developer-Tools', 'Arch_AWS-Command-Line-Interface_64.svg'],
  'fault injection': ['Arch_Developer-Tools', 'Arch_AWS-Fault-Injection-Service_64.svg'],
  'fis': ['Arch_Developer-Tools', 'Arch_AWS-Fault-Injection-Service_64.svg'],
  'infrastructure composer': ['Arch_Developer-Tools', 'Arch_AWS-Infrastructure-Composer_64.svg'],
  'tools and sdks': ['Arch_Developer-Tools', 'Arch_AWS-Tools-and-SDKs_64.svg'],
  'sdk': ['Arch_Developer-Tools', 'Arch_AWS-Tools-and-SDKs_64.svg'],
  'x-ray': ['Arch_Developer-Tools', 'Arch_AWS-X-Ray_64.svg'],
  'xray': ['Arch_Developer-Tools', 'Arch_AWS-X-Ray_64.svg'],
  'codecatalyst': ['Arch_Developer-Tools', 'Arch_Amazon-CodeCatalyst_64.svg'],
  'code catalyst': ['Arch_Developer-Tools', 'Arch_Amazon-CodeCatalyst_64.svg'],
  'corretto': ['Arch_Developer-Tools', 'Arch_Amazon-Corretto_64.svg'],

  // ============================================
  // END USER COMPUTING (2 services)
  // ============================================
  'appstream': ['Arch_End-User-Computing', 'Arch_Amazon-AppStream-2_64.svg'],
  'workspaces': ['Arch_End-User-Computing', 'Arch_Amazon-WorkSpaces-Family_64.svg'],

  // ============================================
  // FRONT-END WEB & MOBILE (3 services)
  // ============================================
  'amplify': ['Arch_Front-End-Web-Mobile', 'Arch_AWS-Amplify_64.svg'],
  'device farm': ['Arch_Front-End-Web-Mobile', 'Arch_AWS-Device-Farm_64.svg'],
  'location service': ['Arch_Front-End-Web-Mobile', 'Arch_Amazon-Location-Service_64.svg'],
  'location': ['Arch_Front-End-Web-Mobile', 'Arch_Amazon-Location-Service_64.svg'],

  // ============================================
  // GAMES (3 services)
  // ============================================
  'gamelift servers': ['Arch_Games', 'Arch_Amazon-GameLift-Servers_64.svg'],
  'gamelift streams': ['Arch_Games', 'Arch_Amazon-GameLift-Streams_64.svg'],
  'gamelift': ['Arch_Games', 'Arch_Amazon-GameLift-Servers_64.svg'],
  'open 3d engine': ['Arch_Games', 'Arch_Open-3D-Engine_64.svg'],
  'o3de': ['Arch_Games', 'Arch_Open-3D-Engine_64.svg'],

  // ============================================
  // IOT (12 services)
  // ============================================
  'iot analytics': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-Analytics_64.svg'],
  'iot button': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-Button_64.svg'],
  'iot core': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-Core_64.svg'],
  'iot device defender': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-Device-Defender_64.svg'],
  'iot device management': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-Device-Management_64.svg'],
  'iot events': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-Events_64.svg'],
  'iot expresslink': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-ExpressLink_64.svg'],
  'iot fleetwise': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-FleetWise_64.svg'],
  'iot greengrass': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-Greengrass_64.svg'],
  'greengrass': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-Greengrass_64.svg'],
  'iot sitewise': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-SiteWise_64.svg'],
  'iot twinmaker': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-TwinMaker_64.svg'],
  'iot': ['Arch_Internet-of-Things', 'Arch_AWS-IoT-Core_64.svg'],
  'freertos': ['Arch_Internet-of-Things', 'Arch_FreeRTOS_64.svg'],

  // ============================================
  // MANAGEMENT & GOVERNANCE (32 services)
  // ============================================
  'appconfig': ['Arch_Management-Governance', 'Arch_AWS-AppConfig_64.svg'],
  'app config': ['Arch_Management-Governance', 'Arch_AWS-AppConfig_64.svg'],
  'application auto scaling': ['Arch_Management-Governance', 'Arch_AWS-Application-Auto-Scaling_64.svg'],
  'backint agent': ['Arch_Management-Governance', 'Arch_AWS-Backint-Agent_64.svg'],
  'chatbot': ['Arch_Management-Governance', 'Arch_AWS-Chatbot_64.svg'],
  'cloudformation': ['Arch_Management-Governance', 'Arch_AWS-CloudFormation_64.svg'],
  'cloud formation': ['Arch_Management-Governance', 'Arch_AWS-CloudFormation_64.svg'],
  'cloudtrail': ['Arch_Management-Governance', 'Arch_AWS-CloudTrail_64.svg'],
  'cloud trail': ['Arch_Management-Governance', 'Arch_AWS-CloudTrail_64.svg'],
  'config': ['Arch_Management-Governance', 'Arch_AWS-Config_64.svg'],
  'console mobile': ['Arch_Management-Governance', 'Arch_AWS-Console-Mobile-Application_64.svg'],
  'control tower': ['Arch_Management-Governance', 'Arch_AWS-Control-Tower_64.svg'],
  'opentelemetry': ['Arch_Management-Governance', 'Arch_AWS-Distro-for-OpenTelemetry_64.svg'],
  'otel': ['Arch_Management-Governance', 'Arch_AWS-Distro-for-OpenTelemetry_64.svg'],
  'health dashboard': ['Arch_Management-Governance', 'Arch_AWS-Health-Dashboard_64.svg'],
  'launch wizard': ['Arch_Management-Governance', 'Arch_AWS-Launch-Wizard_64.svg'],
  'license manager': ['Arch_Management-Governance', 'Arch_AWS-License-Manager_64.svg'],
  'management console': ['Arch_Management-Governance', 'Arch_AWS-Management-Console_64.svg'],
  'organizations': ['Arch_Management-Governance', 'Arch_AWS-Organizations_64.svg'],
  'proton': ['Arch_Management-Governance', 'Arch_AWS-Proton_64.svg'],
  'resilience hub': ['Arch_Management-Governance', 'Arch_AWS-Resilience-Hub_64.svg'],
  'resource explorer': ['Arch_Management-Governance', 'Arch_AWS-Resource-Explorer_64.svg'],
  'service catalog': ['Arch_Management-Governance', 'Arch_AWS-Service-Catalog_64.svg'],
  'service management connector': ['Arch_Management-Governance', 'Arch_AWS-Service-Management-Connector_64.svg'],
  'systems manager': ['Arch_Management-Governance', 'Arch_AWS-Systems-Manager_64.svg'],
  'ssm': ['Arch_Management-Governance', 'Arch_AWS-Systems-Manager_64.svg'],
  'telco network builder': ['Arch_Management-Governance', 'Arch_AWS-Telco-Network-Builder_64.svg'],
  'trusted advisor': ['Arch_Management-Governance', 'Arch_AWS-Trusted-Advisor_64.svg'],
  'user notifications': ['Arch_Management-Governance', 'Arch_AWS-User-Notifications_64.svg'],
  'well-architected': ['Arch_Management-Governance', 'Arch_AWS-Well-Architected-Tool_64.svg'],
  'cloudwatch': ['Arch_Management-Governance', 'Arch_Amazon-CloudWatch_64.svg'],
  'cloud watch': ['Arch_Management-Governance', 'Arch_Amazon-CloudWatch_64.svg'],
  'managed grafana': ['Arch_Management-Governance', 'Arch_Amazon-Managed-Grafana_64.svg'],
  'grafana': ['Arch_Management-Governance', 'Arch_Amazon-Managed-Grafana_64.svg'],
  'managed prometheus': ['Arch_Management-Governance', 'Arch_Amazon-Managed-Service-for-Prometheus_64.svg'],
  'prometheus': ['Arch_Management-Governance', 'Arch_Amazon-Managed-Service-for-Prometheus_64.svg'],

  // ============================================
  // MEDIA SERVICES (20 services)
  // ============================================
  'deadline cloud': ['Arch_Media-Services', 'Arch_AWS-Deadline-Cloud_64.svg'],
  'elemental appliances': ['Arch_Media-Services', 'Arch_AWS-Elemental-Appliances-&-Software_64.svg'],
  'elemental conductor': ['Arch_Media-Services', 'Arch_AWS-Elemental-Conductor_64.svg'],
  'elemental delta': ['Arch_Media-Services', 'Arch_AWS-Elemental-Delta_64.svg'],
  'elemental link': ['Arch_Media-Services', 'Arch_AWS-Elemental-Link_64.svg'],
  'elemental live': ['Arch_Media-Services', 'Arch_AWS-Elemental-Live_64.svg'],
  'mediaconnect': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaConnect_64.svg'],
  'media connect': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaConnect_64.svg'],
  'mediaconvert': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaConvert_64.svg'],
  'media convert': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaConvert_64.svg'],
  'medialive': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaLive_64.svg'],
  'media live': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaLive_64.svg'],
  'mediapackage': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaPackage_64.svg'],
  'media package': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaPackage_64.svg'],
  'mediastore': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaStore_64.svg'],
  'media store': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaStore_64.svg'],
  'mediatailor': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaTailor_64.svg'],
  'media tailor': ['Arch_Media-Services', 'Arch_AWS-Elemental-MediaTailor_64.svg'],
  'elemental server': ['Arch_Media-Services', 'Arch_AWS-Elemental-Server_64.svg'],
  'thinkbox deadline': ['Arch_Media-Services', 'Arch_AWS-Thinkbox-Deadline_64.svg'],
  'thinkbox frost': ['Arch_Media-Services', 'Arch_AWS-Thinkbox-Frost_64.svg'],
  'thinkbox krakatoa': ['Arch_Media-Services', 'Arch_AWS-Thinkbox-Krakatoa_64.svg'],
  'thinkbox sequoia': ['Arch_Media-Services', 'Arch_AWS-Thinkbox-Sequoia_64.svg'],
  'thinkbox stoke': ['Arch_Media-Services', 'Arch_AWS-Thinkbox-Stoke_64.svg'],
  'thinkbox xmesh': ['Arch_Media-Services', 'Arch_AWS-Thinkbox-XMesh_64.svg'],
  'elastic transcoder': ['Arch_Media-Services', 'Arch_Amazon-Elastic-Transcoder_64.svg'],
  'transcoder': ['Arch_Media-Services', 'Arch_Amazon-Elastic-Transcoder_64.svg'],
  'ivs': ['Arch_Media-Services', 'Arch_Amazon-Interactive-Video-Service_64.svg'],
  'interactive video': ['Arch_Media-Services', 'Arch_Amazon-Interactive-Video-Service_64.svg'],

  // ============================================
  // MIGRATION & MODERNIZATION (9 services)
  // ============================================
  'application discovery': ['Arch_Migration-Modernization', 'Arch_AWS-Application-Discovery-Service_64.svg'],
  'application migration': ['Arch_Migration-Modernization', 'Arch_AWS-Application-Migration-Service_64.svg'],
  'mgn': ['Arch_Migration-Modernization', 'Arch_AWS-Application-Migration-Service_64.svg'],
  'data transfer terminal': ['Arch_Migration-Modernization', 'Arch_AWS-Data-Transfer-Terminal_64.svg'],
  'datasync': ['Arch_Migration-Modernization', 'Arch_AWS-DataSync_64.svg'],
  'data sync': ['Arch_Migration-Modernization', 'Arch_AWS-DataSync_64.svg'],
  'mainframe modernization': ['Arch_Migration-Modernization', 'Arch_AWS-Mainframe-Modernization_64.svg'],
  'm2': ['Arch_Migration-Modernization', 'Arch_AWS-Mainframe-Modernization_64.svg'],
  'migration evaluator': ['Arch_Migration-Modernization', 'Arch_AWS-Migration-Evaluator_64.svg'],
  'migration hub': ['Arch_Migration-Modernization', 'Arch_AWS-Migration-Hub_64.svg'],
  'transfer family': ['Arch_Migration-Modernization', 'Arch_AWS-Transfer-Family_64.svg'],
  'transform': ['Arch_Migration-Modernization', 'Arch_AWS-Transform_64.svg'],

  // ============================================
  // NETWORKING & CONTENT DELIVERY (18 services)
  // ============================================
  'app mesh': ['Arch_Networking-Content-Delivery', 'Arch_AWS-App-Mesh_64.svg'],
  'appmesh': ['Arch_Networking-Content-Delivery', 'Arch_AWS-App-Mesh_64.svg'],
  'client vpn': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Client-VPN_64.svg'],
  'cloud map': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Cloud-Map_64.svg'],
  'cloudmap': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Cloud-Map_64.svg'],
  'cloud wan': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Cloud-WAN_64.svg'],
  'direct connect': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Direct-Connect_64.svg'],
  'dx': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Direct-Connect_64.svg'],
  'global accelerator': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Global-Accelerator_64.svg'],
  'private 5g': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Private-5G_64.svg'],
  'privatelink': ['Arch_Networking-Content-Delivery', 'Arch_AWS-PrivateLink_64.svg'],
  'private link': ['Arch_Networking-Content-Delivery', 'Arch_AWS-PrivateLink_64.svg'],
  'site-to-site vpn': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Site-to-Site-VPN_64.svg'],
  'vpn': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Site-to-Site-VPN_64.svg'],
  'transit gateway': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Transit-Gateway_64.svg'],
  'tgw': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Transit-Gateway_64.svg'],
  'verified access': ['Arch_Networking-Content-Delivery', 'Arch_AWS-Verified-Access_64.svg'],
  'api gateway': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-API-Gateway_64.svg'],
  'apigateway': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-API-Gateway_64.svg'],
  'application recovery controller': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-Application-Recovery-Controller_64.svg'],
  'arc': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-Application-Recovery-Controller_64.svg'],
  'cloudfront': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-CloudFront_64.svg'],
  'cloud front': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-CloudFront_64.svg'],
  'cdn': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-CloudFront_64.svg'],
  'route 53': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-Route-53_64.svg'],
  'route53': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-Route-53_64.svg'],
  'dns': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-Route-53_64.svg'],
  'vpc lattice': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-VPC-Lattice_64.svg'],
  'vpc': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-Virtual-Private-Cloud_64.svg'],
  'virtual private cloud': ['Arch_Networking-Content-Delivery', 'Arch_Amazon-Virtual-Private-Cloud_64.svg'],
  'elb': ['Arch_Networking-Content-Delivery', 'Arch_Elastic-Load-Balancing_64.svg'],
  'alb': ['Arch_Networking-Content-Delivery', 'Arch_Elastic-Load-Balancing_64.svg'],
  'nlb': ['Arch_Networking-Content-Delivery', 'Arch_Elastic-Load-Balancing_64.svg'],
  'load balancer': ['Arch_Networking-Content-Delivery', 'Arch_Elastic-Load-Balancing_64.svg'],
  'load balancing': ['Arch_Networking-Content-Delivery', 'Arch_Elastic-Load-Balancing_64.svg'],

  // ============================================
  // QUANTUM TECHNOLOGIES (1 service)
  // ============================================
  'braket': ['Arch_Quantum-Technologies', 'Arch_Amazon-Braket_64.svg'],
  'quantum': ['Arch_Quantum-Technologies', 'Arch_Amazon-Braket_64.svg'],

  // ============================================
  // SATELLITE (1 service)
  // ============================================
  'ground station': ['Arch_Satellite', 'Arch_AWS-Ground-Station_64.svg'],
  'satellite': ['Arch_Satellite', 'Arch_AWS-Ground-Station_64.svg'],

  // ============================================
  // SECURITY, IDENTITY & COMPLIANCE (26 services)
  // ============================================
  'artifact': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Artifact_64.svg'],
  'audit manager': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Audit-Manager_64.svg'],
  'acm': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Certificate-Manager_64.svg'],
  'certificate manager': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Certificate-Manager_64.svg'],
  'certificate': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Certificate-Manager_64.svg'],
  'cloudhsm': ['Arch_Security-Identity-Compliance', 'Arch_AWS-CloudHSM_64.svg'],
  'hsm': ['Arch_Security-Identity-Compliance', 'Arch_AWS-CloudHSM_64.svg'],
  'directory service': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Directory-Service_64.svg'],
  'firewall manager': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Firewall-Manager_64.svg'],
  'iam identity center': ['Arch_Security-Identity-Compliance', 'Arch_AWS-IAM-Identity-Center_64.svg'],
  'sso': ['Arch_Security-Identity-Compliance', 'Arch_AWS-IAM-Identity-Center_64.svg'],
  'iam': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Identity-and-Access-Management_64.svg'],
  'identity': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Identity-and-Access-Management_64.svg'],
  'kms': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Key-Management-Service_64.svg'],
  'key management': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Key-Management-Service_64.svg'],
  'network firewall': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Network-Firewall_64.svg'],
  'firewall': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Network-Firewall_64.svg'],
  'payment cryptography': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Payment-Cryptography_64.svg'],
  'private ca': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Private-Certificate-Authority_64.svg'],
  'pca': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Private-Certificate-Authority_64.svg'],
  'ram': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Resource-Access-Manager_64.svg'],
  'resource access manager': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Resource-Access-Manager_64.svg'],
  'secrets manager': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Secrets-Manager_64.svg'],
  'secrets': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Secrets-Manager_64.svg'],
  'security hub': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Security-Hub_64.svg'],
  'security incident response': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Security-Incident-Response_64.svg'],
  'shield': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Shield_64.svg'],
  'signer': ['Arch_Security-Identity-Compliance', 'Arch_AWS-Signer_64.svg'],
  'waf': ['Arch_Security-Identity-Compliance', 'Arch_AWS-WAF_64.svg'],
  'web application firewall': ['Arch_Security-Identity-Compliance', 'Arch_AWS-WAF_64.svg'],
  'cloud directory': ['Arch_Security-Identity-Compliance', 'Arch_Amazon-Cloud-Directory_64.svg'],
  'cognito': ['Arch_Security-Identity-Compliance', 'Arch_Amazon-Cognito_64.svg'],
  'detective': ['Arch_Security-Identity-Compliance', 'Arch_Amazon-Detective_64.svg'],
  'guardduty': ['Arch_Security-Identity-Compliance', 'Arch_Amazon-GuardDuty_64.svg'],
  'guard duty': ['Arch_Security-Identity-Compliance', 'Arch_Amazon-GuardDuty_64.svg'],
  'inspector': ['Arch_Security-Identity-Compliance', 'Arch_Amazon-Inspector_64.svg'],
  'macie': ['Arch_Security-Identity-Compliance', 'Arch_Amazon-Macie_64.svg'],
  'security lake': ['Arch_Security-Identity-Compliance', 'Arch_Amazon-Security-Lake_64.svg'],
  'verified permissions': ['Arch_Security-Identity-Compliance', 'Arch_Amazon-Verified-Permissions_64.svg'],

  // ============================================
  // STORAGE (16 services)
  // ============================================
  'backup': ['Arch_Storage', 'Arch_AWS-Backup_64.svg'],
  'elastic disaster recovery': ['Arch_Storage', 'Arch_AWS-Elastic-Disaster-Recovery_64.svg'],
  'drs': ['Arch_Storage', 'Arch_AWS-Elastic-Disaster-Recovery_64.svg'],
  'snowball edge': ['Arch_Storage', 'Arch_AWS-Snowball-Edge_64.svg'],
  'snowball': ['Arch_Storage', 'Arch_AWS-Snowball_64.svg'],
  'snow': ['Arch_Storage', 'Arch_AWS-Snowball_64.svg'],
  'storage gateway': ['Arch_Storage', 'Arch_AWS-Storage-Gateway_64.svg'],
  'efs': ['Arch_Storage', 'Arch_Amazon-EFS_64.svg'],
  'elastic file system': ['Arch_Storage', 'Arch_Amazon-EFS_64.svg'],
  'ebs': ['Arch_Storage', 'Arch_Amazon-Elastic-Block-Store_64.svg'],
  'elastic block store': ['Arch_Storage', 'Arch_Amazon-Elastic-Block-Store_64.svg'],
  'fsx for lustre': ['Arch_Storage', 'Arch_Amazon-FSx-for-Lustre_64.svg'],
  'fsx lustre': ['Arch_Storage', 'Arch_Amazon-FSx-for-Lustre_64.svg'],
  'fsx ontap': ['Arch_Storage', 'Arch_Amazon-FSx-for-NetApp-ONTAP_64.svg'],
  'fsx netapp': ['Arch_Storage', 'Arch_Amazon-FSx-for-NetApp-ONTAP_64.svg'],
  'fsx openzfs': ['Arch_Storage', 'Arch_Amazon-FSx-for-OpenZFS_64.svg'],
  'fsx zfs': ['Arch_Storage', 'Arch_Amazon-FSx-for-OpenZFS_64.svg'],
  'fsx windows': ['Arch_Storage', 'Arch_Amazon-FSx-for-WFS_64.svg'],
  'fsx wfs': ['Arch_Storage', 'Arch_Amazon-FSx-for-WFS_64.svg'],
  'fsx': ['Arch_Storage', 'Arch_Amazon-FSx_64.svg'],
  'file cache': ['Arch_Storage', 'Arch_Amazon-File-Cache_64.svg'],
  's3 outposts': ['Arch_Storage', 'Arch_Amazon-S3-on-Outposts_64.svg'],
  'glacier': ['Arch_Storage', 'Arch_Amazon-Simple-Storage-Service-Glacier_64.svg'],
  's3 glacier': ['Arch_Storage', 'Arch_Amazon-Simple-Storage-Service-Glacier_64.svg'],
  's3': ['Arch_Storage', 'Arch_Amazon-Simple-Storage-Service_64.svg'],
  'simple storage': ['Arch_Storage', 'Arch_Amazon-Simple-Storage-Service_64.svg'],
};

// ============================================
// SERVICE ICON FUNCTION
// ============================================

/**
 * Map AWS service name to its icon path.
 * Searches through all 307 AWS service icons.
 */
export function getServiceIcon(serviceName: string): string {
  if (!serviceName) {
    return getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Generic-Application_48_Light.svg');
  }

  const nameLower = serviceName.toLowerCase().trim();
  
  // First, try exact matches in the map
  if (SERVICE_ICON_MAP[nameLower]) {
    const [category, filename] = SERVICE_ICON_MAP[nameLower];
    return getArchitectureIcon(category, 64, filename);
  }
  
  // Then try partial matches (search through all keys)
  for (const [keyword, [category, filename]] of Object.entries(SERVICE_ICON_MAP)) {
    if (nameLower.includes(keyword) || keyword.includes(nameLower)) {
      return getArchitectureIcon(category, 64, filename);
    }
  }
  
  // Default fallback
  return getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Generic-Application_48_Light.svg');
}

// ============================================
// DATABASE ENGINE ICON FUNCTION
// ============================================

/**
 * Map database engine to its icon path
 */
export function getDatabaseIcon(engine: string): string {
  if (!engine) {
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-RDS_64.svg');
  }
  
  const engineLower = engine.toLowerCase();

  // Check specific database types (order matters - specific first)
  if (engineLower.includes('dynamodb') || engineLower.includes('dynamo'))
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-DynamoDB_64.svg');
  if (engineLower.includes('aurora'))
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-Aurora_64.svg');
  if (engineLower.includes('documentdb') || engineLower.includes('mongo'))
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-DocumentDB_64.svg');
  if (engineLower.includes('elasticache') || engineLower.includes('redis') || engineLower.includes('memcached'))
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-ElastiCache_64.svg');
  if (engineLower.includes('neptune'))
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-Neptune_64.svg');
  if (engineLower.includes('timestream'))
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-Timestream_64.svg');
  if (engineLower.includes('keyspaces') || engineLower.includes('cassandra'))
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-Keyspaces_64.svg');
  if (engineLower.includes('memorydb'))
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-MemoryDB_64.svg');
  if (engineLower.includes('redshift'))
    return getArchitectureIcon('Arch_Analytics', 64, 'Arch_Amazon-Redshift_64.svg');
  if (engineLower.includes('qldb') || engineLower.includes('quantum ledger'))
    return getArchitectureIcon('Arch_Blockchain', 64, 'Arch_Amazon-Quantum-Ledger-Database_64.svg');
    
  // RDS variants (postgres, mysql, etc.)
  if (engineLower.includes('postgres') || engineLower.includes('mysql') || 
      engineLower.includes('mariadb') || engineLower.includes('oracle') || 
      engineLower.includes('sqlserver') || engineLower.includes('sql server') ||
      engineLower.includes('rds'))
    return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-RDS_64.svg');

  // Default to RDS
  return getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-RDS_64.svg');
}

// ============================================
// GENERIC ICONS
// ============================================

/**
 * Get generic icons
 */
export const GENERIC_ICONS = {
  user: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_User_48_Light.svg'),
  users: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Users_48_Light.svg'),
  table: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Data-Table_48_Light.svg'),
  database: getArchitectureIcon('Arch_Database', 64, 'Arch_Amazon-RDS_64.svg'),
  server: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Server_48_Light.svg'),
  servers: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Servers_48_Light.svg'),
  globe: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Globe_48_Light.svg'),
  internet: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Internet_48_Light.svg'),
  document: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Document_48_Light.svg'),
  folder: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Folder_48_Light.svg'),
  gear: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Gear_48_Light.svg'),
  shield: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Shield_48_Light.svg'),
  alert: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Alert_48_Light.svg'),
  email: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Email_48_Light.svg'),
  client: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Client_48_Light.svg'),
  mobile: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Mobile-client_48_Light.svg'),
  generic: getResourceIcon('Res_General-Icons', 'Res_48_Light', 'Res_Generic-Application_48_Light.svg'),
} as const;

// ============================================
// VERSION INFO
// ============================================

/**
 * Get current AWS icons version
 */
export function getIconsVersion(): string {
  return AWS_ICONS_VERSION;
}

/**
 * Get formatted version date
 */
export function getIconsVersionDate(): string {
  const month = AWS_ICONS_VERSION.slice(0, 2);
  const day = AWS_ICONS_VERSION.slice(2, 4);
  const year = AWS_ICONS_VERSION.slice(4, 8);
  return `${month}/${day}/${year}`;
}

/**
 * Get the total number of mapped services
 */
export function getMappedServiceCount(): number {
  return Object.keys(SERVICE_ICON_MAP).length;
}

// ============================================
// CATEGORY ICON MAP
// ============================================

/**
 * AWS resource categories with their icon filenames
 */
const CATEGORY_ICON_MAP: Record<string, string> = {
  'analytics': 'Arch-Category_Analytics_64.svg',
  'app-integration': 'Arch-Category_Application-Integration_64.svg',
  'artificial-intelligence': 'Arch-Category_Artificial-Intelligence_64.svg',
  'blockchain': 'Arch-Category_Blockchain_64.svg',
  'business-applications': 'Arch-Category_Business-Applications_64.svg',
  'cloud-financial-management': 'Arch-Category_Cloud-Financial-Management_64.svg',
  'compute': 'Arch-Category_Compute_64.svg',
  'contact-center': 'Arch-Category_Contact-Center_64.svg',
  'containers': 'Arch-Category_Containers_64.svg',
  'customer-enablement': 'Arch-Category_Customer-Enablement_64.svg',
  'database': 'Arch-Category_Database_64.svg',
  'developer-tools': 'Arch-Category_Developer-Tools_64.svg',
  'end-user-computing': 'Arch-Category_End-User-Computing_64.svg',
  'front-end-web-mobile': 'Arch-Category_Front-End-Web-Mobile_64.svg',
  'games': 'Arch-Category_Games_64.svg',
  'internet-of-things': 'Arch-Category_Internet-of-Things_64.svg',
  'management-governance': 'Arch-Category_Management-Governance_64.svg',
  'media-services': 'Arch-Category_Media-Services_64.svg',
  'migration-modernization': 'Arch-Category_Migration-Modernization_64.svg',
  'networking-content-delivery': 'Arch-Category_Networking-Content-Delivery_64.svg',
  'quantum-technologies': 'Arch-Category_Quantum-Technologies_64.svg',
  'satellite': 'Arch-Category_Satellite_64.svg',
  'security-identity-compliance': 'Arch-Category_Security-Identity-Compliance_64.svg',
  'serverless': 'Arch-Category_Serverless_64.svg',
  'storage': 'Arch-Category_Storage_64.svg',
};

/**
 * Get AWS category icon path by category name
 * @param category - Category name (e.g., 'compute', 'database', 'storage')
 * @returns Full path to the category icon
 */
export function getCategoryIconByName(category: string): string {
  const categoryLower = category.toLowerCase().trim();
  const filename = CATEGORY_ICON_MAP[categoryLower];

  if (filename) {
    return getCategoryIcon(64, filename);
  }

  // Default to compute icon if category not found
  return getCategoryIcon(64, 'Arch-Category_Compute_64.svg');
}
