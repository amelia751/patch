/**
 * Google Cloud Platform Icon Library
 * 
 * Maps GCP service names to their official icon paths.
 * Icons are stored in /public/gcp-icons/
 * 
 * Structure:
 * - unique-icons/: High-quality product icons (512px SVGs)
 * - google-cloud-legacy-icons/: Individual service icons (SVGs)
 * - category-icons/: Category-level icons
 */

// Base paths for GCP icons
const GCP_ICON_BASE = "/gcp-icons";
const UNIQUE_BASE = `${GCP_ICON_BASE}/unique-icons`;
const LEGACY_BASE = `${GCP_ICON_BASE}/google-cloud-legacy-icons`;
const CATEGORY_BASE = `${GCP_ICON_BASE}/category-icons`;
const FIREBASE_BASE = `${GCP_ICON_BASE}/firebase-icons`;

// GCP service to icon mapping
// Priority: unique-icons > legacy-icons > category-icons
// NOTE: Filenames vary - some have -rgb suffix, some don't. Verify in /public/gcp-icons/
const GCP_SERVICE_ICONS: Record<string, string> = {
  // Compute
  "cloud run": `${UNIQUE_BASE}/Cloud Run/SVG/CloudRun-512-color-rgb.svg`,
  "cloud functions": `${LEGACY_BASE}/cloud_functions/cloud_functions.svg`,
  "compute engine": `${UNIQUE_BASE}/Compute Engine/SVG/ComputeEngine-512-color-rgb.svg`,
  "gke": `${UNIQUE_BASE}/GKE/SVG/GKE-512-color.svg`,
  "kubernetes engine": `${UNIQUE_BASE}/GKE/SVG/GKE-512-color.svg`,
  "app engine": `${LEGACY_BASE}/app_engine/app_engine.svg`,
  
  // Database
  "cloud sql": `${UNIQUE_BASE}/Cloud SQL/SVG/CloudSQL-512-color.svg`,
  "cloud spanner": `${UNIQUE_BASE}/Cloud Spanner/SVG/CloudSpanner-512-color.svg`,
  "alloydb": `${UNIQUE_BASE}/AlloyDB/SVG/AlloyDB-512-color.svg`,
  "firestore": `${FIREBASE_BASE}/Product_Logomark_Cloud_Firestore_Full_Color.svg`,
  "cloud firestore": `${FIREBASE_BASE}/Product_Logomark_Cloud_Firestore_Full_Color.svg`,
  "bigtable": `${LEGACY_BASE}/bigtable/bigtable.svg`,
  "memorystore": `${LEGACY_BASE}/memorystore/memorystore.svg`,
  "firebase realtime database": `${FIREBASE_BASE}/Firebase Realtime Database_Standalone logomark.svg`,
  
  // Storage
  "cloud storage": `${UNIQUE_BASE}/Cloud Storage/SVG/Cloud_Storage-512-color.svg`,
  "gcs": `${UNIQUE_BASE}/Cloud Storage/SVG/Cloud_Storage-512-color.svg`,
  "storage": `${UNIQUE_BASE}/Cloud Storage/SVG/Cloud_Storage-512-color.svg`,
  
  // Networking
  "api gateway": `${LEGACY_BASE}/api/api.svg`,
  "cloud load balancing": `${LEGACY_BASE}/cloud_load_balancing/cloud_load_balancing.svg`,
  "load balancer": `${LEGACY_BASE}/cloud_load_balancing/cloud_load_balancing.svg`,
  "cloud cdn": `${LEGACY_BASE}/cloud_cdn/cloud_cdn.svg`,
  "cloud armor": `${LEGACY_BASE}/cloud_armor/cloud_armor.svg`,
  "cloud dns": `${LEGACY_BASE}/cloud_dns/cloud_dns.svg`,
  "vpc": `${LEGACY_BASE}/virtual_private_cloud/virtual_private_cloud.svg`,
  "cloud nat": `${LEGACY_BASE}/cloud_nat/cloud_nat.svg`,
  "cloud router": `${LEGACY_BASE}/cloud_router/cloud_router.svg`,
  
  // Security & Identity
  "identity platform": `${LEGACY_BASE}/identity_platform/identity_platform.svg`,
  "cloud iam": `${LEGACY_BASE}/cloud_iam/cloud_iam.svg`,
  "iam": `${LEGACY_BASE}/cloud_iam/cloud_iam.svg`,
  "secret manager": `${LEGACY_BASE}/secret_manager/secret_manager.svg`,
  "cloud kms": `${LEGACY_BASE}/key_management_service/key_management_service.svg`,
  "key management service": `${LEGACY_BASE}/key_management_service/key_management_service.svg`,
  "firebase auth": `${FIREBASE_BASE}/Product_Logomark_Authentication_Full_Color.svg`,
  "firebase authentication": `${FIREBASE_BASE}/Product_Logomark_Authentication_Full_Color.svg`,
  
  // Analytics & Big Data
  "bigquery": `${UNIQUE_BASE}/BigQuery/SVG/BigQuery-512-color.svg`,
  "dataflow": `${LEGACY_BASE}/dataflow/dataflow.svg`,
  "dataproc": `${LEGACY_BASE}/dataproc/dataproc.svg`,
  "pub/sub": `${LEGACY_BASE}/pubsub/pubsub.svg`,
  "pubsub": `${LEGACY_BASE}/pubsub/pubsub.svg`,
  
  // AI/ML
  "vertex ai": `${UNIQUE_BASE}/Vertex AI/SVG/VertexAI-512-color.svg`,
  "vertex ai prediction": `${UNIQUE_BASE}/Vertex AI/SVG/VertexAI-512-color.svg`,
  "ai platform": `${UNIQUE_BASE}/Vertex AI/SVG/VertexAI-512-color.svg`,
  "gemini": `${UNIQUE_BASE}/Vertex AI/SVG/VertexAI-512-color.svg`,
  "gemini api": `${UNIQUE_BASE}/Vertex AI/SVG/VertexAI-512-color.svg`,
  "imagen": `${UNIQUE_BASE}/AI Hypercomputer/SVG/AIHypercomputer-512-color.svg`,
  "ai hypercomputer": `${UNIQUE_BASE}/AI Hypercomputer/SVG/AIHypercomputer-512-color.svg`,
  "automl": `${LEGACY_BASE}/automl/automl.svg`,
  "document ai": `${LEGACY_BASE}/document_ai/document_ai.svg`,
  "documentai": `${LEGACY_BASE}/document_ai/document_ai.svg`,
  
  // Management & Monitoring
  "cloud monitoring": `${LEGACY_BASE}/cloud_monitoring/cloud_monitoring.svg`,
  "monitoring": `${LEGACY_BASE}/cloud_monitoring/cloud_monitoring.svg`,
  "cloud logging": `${LEGACY_BASE}/cloud_logging/cloud_logging.svg`,
  "logging": `${LEGACY_BASE}/cloud_logging/cloud_logging.svg`,
  "cloud trace": `${LEGACY_BASE}/trace/trace.svg`,
  "trace": `${LEGACY_BASE}/trace/trace.svg`,
  
  // Integration
  "cloud tasks": `${LEGACY_BASE}/cloud_tasks/cloud_tasks.svg`,
  "cloud scheduler": `${LEGACY_BASE}/cloud_scheduler/cloud_scheduler.svg`,
  "cloud composer": `${LEGACY_BASE}/cloud_composer/cloud_composer.svg`,
  "workflows": `${LEGACY_BASE}/workflows/workflows.svg`,
  "eventarc": `${LEGACY_BASE}/eventarc/eventarc.svg`,
  
  // API Management
  "apigee": `${UNIQUE_BASE}/Apigee/SVG/Apigee-512-color-rgb.svg`,

  // Firebase Services
  "firebase": `${FIREBASE_BASE}/Product_Logomark_Authentication_Full_Color.svg`,
  "firebase storage": `${FIREBASE_BASE}/Product_Logomark_Cloud_Storage_Full_Color.svg`,
  "firebase cloud storage": `${FIREBASE_BASE}/Product_Logomark_Cloud_Storage_Full_Color.svg`,
  "firebase functions": `${FIREBASE_BASE}/Product_Logomark_Cloud_Functions_Full_Color.svg`,
  "firebase cloud functions": `${FIREBASE_BASE}/Product_Logomark_Cloud_Functions_Full_Color.svg`,
  "firebase hosting": `${FIREBASE_BASE}/Product_Logomark_Hosting_Full_Color.svg`,
  "firebase analytics": `${FIREBASE_BASE}/Product_Logomark_Analytics_Full_Color.svg`,
  "firebase crashlytics": `${FIREBASE_BASE}/Product_Logomark_Crashlytics_Full_Color.svg`,
  "firebase performance monitoring": `${FIREBASE_BASE}/Firebase Performance Monitoring_Standalone logomark.svg`,
  "firebase cloud messaging": `${FIREBASE_BASE}/Product_Logomark_Cloud_Messaging_Full_Color.svg`,
  "firebase remote config": `${FIREBASE_BASE}/Firebase Remote Config_Standalone logomark.svg`,
  "firebase test lab": `${FIREBASE_BASE}/Firebase Test Lab_Standalone logomark.svg`,
};

// Default GCP icon for unknown services (generic compute icon)
const DEFAULT_GCP_ICON = `${CATEGORY_BASE}/Compute/SVG/Compute-512-color.svg`;

/**
 * Get the icon path for a GCP service
 */
export function getGCPServiceIcon(service: string): string {
  const serviceLower = service.toLowerCase().trim();
  
  // Check main service icons (exact match)
  if (GCP_SERVICE_ICONS[serviceLower]) {
    return GCP_SERVICE_ICONS[serviceLower];
  }
  
  // Check for partial matches
  for (const [key, path] of Object.entries(GCP_SERVICE_ICONS)) {
    if (serviceLower.includes(key) || key.includes(serviceLower)) {
      return path;
    }
  }
  
  return DEFAULT_GCP_ICON;
}

/**
 * Check if a service is a known GCP service
 */
export function isGCPService(service: string): boolean {
  const serviceLower = service.toLowerCase().trim();
  
  const gcpKeywords = [
    'cloud run', 'cloud sql', 'cloud storage', 'gcs', 'gke', 'bigquery',
    'vertex ai', 'cloud functions', 'compute engine', 'identity platform',
    'cloud monitoring', 'cloud logging', 'pub/sub', 'pubsub', 'firestore',
    'spanner', 'alloydb', 'memorystore', 'bigtable', 'apigee', 'cloud armor',
    'cloud cdn', 'cloud dns', 'secret manager', 'cloud kms', 'dataflow',
    'dataproc', 'cloud composer', 'cloud tasks', 'cloud scheduler',
    'app engine', 'gke', 'kubernetes engine', 'cloud nat', 'vpc',
    'load balancing', 'eventarc', 'workflows', 'automl', 'api gateway',
    'firebase', 'firebase auth', 'firebase storage', 'firebase hosting',
    'firebase analytics', 'firebase functions', 'firebase realtime database',
    'document ai', 'documentai', 'dialogflow', 'translation', 'vision', 'speech'
  ];
  
  return gcpKeywords.some(keyword => 
    serviceLower.includes(keyword) || keyword.includes(serviceLower)
  );
}

/**
 * Get GCP service color
 * Using GCP's official color palette
 *
 * Strategy:
 * - Specific products (Cloud Run, BigQuery, Cloud SQL) get distinct colors
 * - Generic category services (Cloud Load Balancing, Cloud Logging) get light blue
 */
export function getGCPServiceColor(service: string): string {
  const serviceLower = service.toLowerCase();

  // Firebase - All Firebase services use Amber (to differentiate from GCP yellow services)
  // Includes Firebase Auth, Firestore, Firebase Storage, Firebase Functions, etc.
  if (serviceLower.includes('firebase') || serviceLower.includes('firestore')) {
    return '#F59E0B'; // Amber
  }

  // Specific Products - Keep distinct colors

  // Core Compute Products - Blue
  if (serviceLower.includes('cloud run') || serviceLower.includes('compute engine') ||
      serviceLower.includes('gke') || serviceLower.includes('app engine')) {
    return '#4285F4'; // Google Blue
  }

  // Core Database Products - Yellow (but not Firestore, that's Firebase)
  if (serviceLower.includes('cloud sql') || serviceLower.includes('spanner') ||
      serviceLower.includes('bigtable') || serviceLower.includes('alloydb') ||
      serviceLower.includes('memorystore')) {
    return '#FBBC04'; // Google Yellow
  }

  // Cloud Storage (specific product) - Green
  if (serviceLower.includes('cloud storage') || serviceLower.includes('gcs')) {
    return '#34A853'; // Google Green
  }

  // Core Analytics/AI Products - Cyan
  if (serviceLower.includes('bigquery') || serviceLower.includes('vertex ai') ||
      serviceLower.includes('dataflow') || serviceLower.includes('pub/sub') ||
      serviceLower.includes('pubsub') || serviceLower.includes('document ai') ||
      serviceLower.includes('documentai') || serviceLower.includes('dialogflow') ||
      serviceLower.includes('automl') || serviceLower.includes('vision') ||
      serviceLower.includes('speech') || serviceLower.includes('translation')) {
    return '#00BCD4'; // Cyan
  }

  // Cloud Functions (specific product) - Blue
  if (serviceLower.includes('cloud functions')) {
    return '#4285F4'; // Google Blue
  }

  // Generic Category Services - Light Blue
  // These are infrastructure/category services, not specific products

  // Generic Networking services
  if (serviceLower.includes('load balancing') || serviceLower.includes('cloud cdn') ||
      serviceLower.includes('cloud armor') || serviceLower.includes('cloud dns') ||
      serviceLower.includes('cloud nat') || serviceLower.includes('cloud router') ||
      serviceLower.includes('vpc') || serviceLower.includes('api gateway')) {
    return '#5294CF'; // Light Blue (category service)
  }

  // Generic Management/Monitoring services
  if (serviceLower.includes('monitoring') || serviceLower.includes('logging') ||
      serviceLower.includes('trace') || serviceLower.includes('cloud tasks') ||
      serviceLower.includes('cloud scheduler') || serviceLower.includes('workflows') ||
      serviceLower.includes('cloud composer') || serviceLower.includes('eventarc')) {
    return '#5294CF'; // Light Blue (category service)
  }

  // Generic Security services
  if (serviceLower.includes('identity') || serviceLower.includes('iam') ||
      serviceLower.includes('secret manager') || serviceLower.includes('kms')) {
    return '#5294CF'; // Light Blue (category service)
  }

  // Generic Storage services (not Cloud Storage product)
  if (serviceLower.includes('storage')) {
    return '#5294CF'; // Light Blue (category service)
  }

  // Default - Light Blue for generic services
  return '#5294CF';
}

/**
 * Get database icon for GCP
 */
export function getGCPDatabaseIcon(engine: string): string {
  const engineLower = (engine || '').toLowerCase();

  if (engineLower.includes('spanner')) {
    return GCP_SERVICE_ICONS['cloud spanner'] || DEFAULT_GCP_ICON;
  }
  if (engineLower.includes('alloy')) {
    return GCP_SERVICE_ICONS['alloydb'] || DEFAULT_GCP_ICON;
  }
  if (engineLower.includes('firestore')) {
    return GCP_SERVICE_ICONS['firestore'] || DEFAULT_GCP_ICON;
  }
  if (engineLower.includes('firebase') && engineLower.includes('realtime')) {
    return GCP_SERVICE_ICONS['firebase realtime database'] || DEFAULT_GCP_ICON;
  }
  if (engineLower.includes('bigtable')) {
    return GCP_SERVICE_ICONS['bigtable'] || DEFAULT_GCP_ICON;
  }
  if (engineLower.includes('memorystore') || engineLower.includes('redis')) {
    return GCP_SERVICE_ICONS['memorystore'] || DEFAULT_GCP_ICON;
  }

  // Default to Cloud SQL for relational databases (PostgreSQL, MySQL, SQL Server)
  return GCP_SERVICE_ICONS['cloud sql'] || DEFAULT_GCP_ICON;
}

/**
 * Category icon paths for resource groupings
 * Maps resource categories to their GCP category icons
 */
const GCP_CATEGORY_ICON_PATHS: Record<string, string> = {
  "compute": `${CATEGORY_BASE}/Compute/SVG/Compute-512-color.svg`,
  "database": `${CATEGORY_BASE}/Databases/SVG/Databases-512-color.svg`,
  "storage": `${CATEGORY_BASE}/Storage/SVG/Storage-512-color.svg`,
  "networking": `${CATEGORY_BASE}/Networking/SVG/Networking-512-color-rgb.svg`,
  "security": `${CATEGORY_BASE}/Security Identity/SVG/SecurityIdentity-512-color.svg`,
  "ai": `${CATEGORY_BASE}/AI _ Machine Learning/SVG/AIMachineLearning-512-color.svg`,
  "api": `${UNIQUE_BASE}/Apigee/SVG/Apigee-512-color-rgb.svg`,
};

/**
 * Get category icon for resource groupings
 * @param category - The resource category (compute, database, storage, networking, security)
 * @returns Path to the GCP category icon
 */
export function getGCPCategoryIcon(category: string): string {
  const categoryLower = category.toLowerCase().trim();
  return GCP_CATEGORY_ICON_PATHS[categoryLower] || DEFAULT_GCP_ICON;
}
