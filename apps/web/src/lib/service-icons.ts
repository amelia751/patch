/**
 * Service Icons Utility
 * 
 * Provides icons for 3000+ services using a tiered approach:
 * 1. svgl.app - Full color logos (400+ icons)
 * 2. Simple Icons CDN - Monochrome with brand colors (3100+ icons)
 * 3. Lucide - Category-based fallbacks
 * 
 * Usage:
 *   const icon = await getServiceIcon('stripe');
 *   // { type: 'cdn', src: 'https://cdn.simpleicons.org/stripe/635BFF', color: '#635BFF' }
 */

import * as simpleIcons from 'simple-icons';

// ============================================
// TYPES
// ============================================

export type IconType = 'svgl' | 'simple-icons' | 'lucide' | 'local';

export interface ServiceIcon {
  type: IconType;
  /** URL for svgl/simple-icons, or Lucide icon name, or local path */
  src: string;
  /** Brand color (hex) */
  color: string;
  /** Background color for badges/containers */
  bgColor: string;
  /** Original service name */
  title: string;
  /** Slug used for lookup */
  slug: string;
}

// ============================================
// SVGL.APP KNOWN ICONS (Full Color)
// Source: https://github.com/pheralb/svgl/blob/main/src/data/svgs.ts
// URL Pattern: https://svgl.app/library/{file}.svg
// Some icons have light/dark variants - we use the appropriate one
// ============================================

interface SvglIcon {
  /** File path (without .svg) - can be simple or light/dark object */
  file: string | { light: string; dark: string };
  /** Brand color */
  color: string;
}

// ============================================
// LOCAL ICONS (stored in /public/service-icons/)
// Use when CDN icons aren't available or quality is better
// ============================================

interface LocalIcon {
  /** File path relative to /service-icons/ */
  file: string;
  /** Brand color */
  color: string;
}

const LOCAL_ICONS: Record<string, LocalIcon> = {
  // Search - SVG preferred for scalability
  'elasticsearch': { file: 'elasticsearch.svg', color: '#005571' },
  'elastic cloud': { file: 'elasticsearch.svg', color: '#005571' },
  'elastic': { file: 'elasticsearch.svg', color: '#005571' },
};

const SVGL_ICONS: Record<string, SvglIcon> = {
  // Auth & Identity (full color where available)
  // 'clerk': { file: 'clerk', color: '#6C47FF' }, // Use Simple Icons instead for better availability
  'auth0': { file: 'auth0', color: '#EB5424' },
  'firebase': { file: 'firebase', color: '#FFCA28' },
  'supabase': { file: 'supabase', color: '#3FCF8E' }, // Full color available!
  'workos': { file: 'workos', color: '#6363F1' },
  
  // Payments (full color)
  'stripe': { file: 'stripe', color: '#635BFF' },
  'paypal': { file: 'paypal', color: '#003087' },
  
  // Communication & Email
  'twilio': { file: 'twilio', color: '#F22F46' },
  'resend': { file: { light: 'resend-icon-black', dark: 'resend-icon-white' }, color: '#000000' }, // Only mono available
  'postmark': { file: 'postmark', color: '#FFDE00' },
  'sendgrid': { file: 'sendgrid', color: '#1A82E2' },
  
  // Messaging & Chat (full color)
  'slack': { file: 'slack', color: '#4A154B' }, // Full color!
  'discord': { file: 'discord', color: '#5865F2' }, // Full color!
  'telegram': { file: 'telegram', color: '#26A5E4' },
  'whatsapp': { file: 'whatsapp', color: '#25D366' },
  'mattermost': { file: { light: 'mattermost-light', dark: 'mattermost-dark' }, color: '#0058CC' }, // Only mono
  
  // Databases (full color where available)
  'mongodb': { file: 'mongodb', color: '#47A248' },
  'postgresql': { file: 'postgresql', color: '#4169E1' },
  'mysql': { file: 'mysql', color: '#4479A1' },
  'redis': { file: 'redis', color: '#DC382D' },
  'planetscale': { file: 'planetscale', color: '#000000' },
  'neon': { file: 'neon', color: '#00E699' },
  'prisma': { file: { light: 'prisma', dark: 'prisma_dark' }, color: '#2D3748' }, // Corrected paths
  'drizzle': { file: 'drizzle', color: '#C5F74F' },
  
  // Cloud & Hosting
  'vercel': { file: { light: 'vercel', dark: 'vercel_dark' }, color: '#000000' }, // Corrected paths
  'netlify': { file: 'netlify', color: '#00C7B7' },
  'railway': { file: { light: 'railway', dark: 'railway_dark' }, color: '#0B0D0E' }, // Corrected paths
  'render': { file: 'render', color: '#46E3B7' },
  'cloudflare': { file: 'cloudflare', color: '#F38020' },
  'fly': { file: 'fly', color: '#7B3BE2' },
  'heroku': { file: 'heroku', color: '#430098' },
  'digitalocean': { file: 'digitalocean', color: '#0080FF' },
  
  // Analytics & Monitoring (full color)
  'sentry': { file: 'sentry', color: '#362D59' }, // Full color!
  'datadog': { file: 'datadog', color: '#632CA6' }, // Full color!
  'posthog': { file: 'posthog', color: '#1D4AFF' }, // Full color!
  'mixpanel': { file: 'mixpanel', color: '#7856FF' },
  'amplitude': { file: 'amplitude', color: '#1351AF' },
  'grafana': { file: 'grafana', color: '#F46800' },
  
  // AI & ML
  'openai': { file: { light: 'openai', dark: 'openai_dark' }, color: '#412991' }, // Corrected paths
  'anthropic': { file: 'anthropic', color: '#D4A373' },
  'huggingface': { file: 'hugging-face', color: '#FFD21E' },
  'ollama': { file: { light: 'ollama_light', dark: 'ollama_dark' }, color: '#000000' }, // Only mono
  'groq': { file: 'groq', color: '#F55036' },
  'cohere': { file: 'cohere', color: '#39594D' },
  'together ai': { file: 'togetherai', color: '#0066FF' },
  
  // Storage & CDN
  'uploadthing': { file: 'uploadthing', color: '#EF4444' },
  'cloudinary': { file: 'cloudinary', color: '#3448C5' },
  
  // CMS
  'contentful': { file: 'contentful', color: '#2478CC' },
  'sanity': { file: 'sanity', color: '#F03E2F' },
  'strapi': { file: 'strapi', color: '#4945FF' },
  'payload': { file: 'payload', color: '#000000' },
  
  // Search
  'algolia': { file: 'algolia', color: '#003DFF' },
  'typesense': { file: 'typesense', color: '#D52D61' },
  
  // Workflow & Automation
  'n8n': { file: 'n8n', color: '#EA4B71' },
  'inngest': { file: 'inngest', color: '#6366F1' },
  
  // Developer Tools (full color where available)
  'github': { file: { light: 'github_light', dark: 'github_dark' }, color: '#181717' }, // Corrected paths
  'gitlab': { file: 'gitlab', color: '#FC6D26' },
  'bitbucket': { file: 'bitbucket', color: '#0052CC' },
  'figma': { file: 'figma', color: '#F24E1E' },
  'postman': { file: 'postman', color: '#FF6C37' },
  'notion': { file: 'notion', color: '#000000' }, // Full color available!
  'linear': { file: 'linear', color: '#5E6AD2' }, // Full color available!
  'jira': { file: 'jira', color: '#0052CC' },
  'hubspot': { file: 'hubspot', color: '#FF7A59' },
  
  // Social (full color)
  'google': { file: 'google', color: '#4285F4' },
  'microsoft': { file: 'microsoft', color: '#00A4EF' },
  'twitter': { file: { light: 'x', dark: 'x_dark' }, color: '#000000' },
  'x': { file: { light: 'x', dark: 'x_dark' }, color: '#000000' },
  'facebook': { file: 'meta', color: '#0866FF' },
  'linkedin': { file: 'linkedin', color: '#0A66C2' },
  'instagram': { file: 'instagram', color: '#E4405F' },
  'youtube': { file: 'youtube', color: '#FF0000' },
  'tiktok': { file: 'tiktok', color: '#000000' },
  
  // E-commerce
  'shopify': { file: 'shopify', color: '#7AB55C' },
  'woocommerce': { file: 'woocommerce', color: '#96588A' },
  
  // Frameworks (full color where available)
  'react': { file: 'react', color: '#61DAFB' },
  'vue': { file: 'vue', color: '#4FC08D' },
  'angular': { file: 'angular', color: '#DD0031' },
  'svelte': { file: 'svelte', color: '#FF3E00' },
  'nextjs': { file: 'nextjs_icon_dark', color: '#000000' }, // Use the main dark icon (it's the default)
  'nuxt': { file: 'nuxt', color: '#00DC82' },
  'astro': { file: { light: 'astro-icon-light', dark: 'astro-icon-dark' }, color: '#FF5D01' }, // Corrected paths
};

// ============================================
// CATEGORY FALLBACKS (Lucide Icons)
// ============================================

const CATEGORY_FALLBACKS: Record<string, { icon: string; color: string }> = {
  'auth': { icon: 'Shield', color: '#6C47FF' },
  'payment': { icon: 'CreditCard', color: '#635BFF' },
  'email': { icon: 'Mail', color: '#1A82E2' },
  'messaging': { icon: 'MessageSquare', color: '#4A154B' },
  'database': { icon: 'Database', color: '#47A248' },
  'storage': { icon: 'HardDrive', color: '#3448C5' },
  'analytics': { icon: 'BarChart3', color: '#7856FF' },
  'monitoring': { icon: 'Activity', color: '#362D59' },
  'ai': { icon: 'Sparkles', color: '#412991' },
  'search': { icon: 'Search', color: '#003DFF' },
  'cms': { icon: 'FileText', color: '#4945FF' },
  'hosting': { icon: 'Cloud', color: '#000000' },
  'automation': { icon: 'Workflow', color: '#FF4A00' },
  'default': { icon: 'Box', color: '#6B7280' },
};

// ============================================
// HELPER FUNCTIONS
// ============================================

/**
 * Normalize a service name to a slug
 */
function normalizeSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

/**
 * Generate background color from hex (with opacity)
 */
function getBgColor(hex: string, opacity: number = 0.15): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

/**
 * Get Simple Icons data by name/slug
 */
function getSimpleIconData(name: string): { slug: string; hex: string; title: string } | null {
  const normalizedName = normalizeSlug(name);
  
  // Try direct lookup with "si" prefix
  const iconKey = `si${name.charAt(0).toUpperCase()}${name.slice(1).toLowerCase()}` as keyof typeof simpleIcons;
  
  // Search through all icons
  for (const [key, icon] of Object.entries(simpleIcons)) {
    if (key === 'default') continue;
    
    const iconData = icon as { slug?: string; hex?: string; title?: string };
    if (!iconData.slug) continue;
    
    // Match by slug or title
    if (
      iconData.slug === normalizedName ||
      iconData.slug === name.toLowerCase() ||
      iconData.title?.toLowerCase() === name.toLowerCase() ||
      iconData.title?.toLowerCase().replace(/\s+/g, '') === name.toLowerCase()
    ) {
      return {
        slug: iconData.slug,
        hex: iconData.hex || '6B7280',
        title: iconData.title || name,
      };
    }
  }
  
  return null;
}

/**
 * Infer category from service name (for Lucide fallback)
 */
function inferCategory(name: string): string {
  const lower = name.toLowerCase();
  
  if (/auth|clerk|okta|keycloak/.test(lower)) return 'auth';
  if (/stripe|pay|braintree|square/.test(lower)) return 'payment';
  if (/mail|email|sendgrid|ses|postmark|resend/.test(lower)) return 'email';
  if (/slack|discord|teams|chat|twilio/.test(lower)) return 'messaging';
  if (/postgres|mysql|mongo|redis|dynamo|firebase|supabase|planetscale|neon/.test(lower)) return 'database';
  if (/s3|storage|cloudinary|upload/.test(lower)) return 'storage';
  if (/analytics|mixpanel|amplitude|posthog|segment/.test(lower)) return 'analytics';
  if (/sentry|datadog|newrelic|monitor/.test(lower)) return 'monitoring';
  if (/openai|anthropic|ai|ml|bedrock|hugging/.test(lower)) return 'ai';
  if (/algolia|elastic|search|opensearch/.test(lower)) return 'search';
  if (/contentful|sanity|strapi|cms/.test(lower)) return 'cms';
  if (/vercel|netlify|railway|render|heroku/.test(lower)) return 'hosting';
  if (/zapier|n8n|workflow|automate/.test(lower)) return 'automation';
  
  return 'default';
}

// ============================================
// MAIN API
// ============================================

/**
 * Get service icon with tiered fallback:
 * 1. SVGL (full color) - if in known list
 * 2. Simple Icons CDN (mono + color) - if found in package
 * 3. Lucide (category fallback) - always works
 * 
 * @param name - Service name (e.g., "stripe", "resend")
 * @param theme - Optional theme for light/dark variants ('light' | 'dark')
 */
export function getServiceIcon(name: string, theme: 'light' | 'dark' = 'light'): ServiceIcon {
  const slug = normalizeSlug(name);
  
  // 0. Check local icons first (highest quality, no CDN dependency)
  const localIcon = LOCAL_ICONS[slug] || LOCAL_ICONS[name.toLowerCase()];
  if (localIcon) {
    return {
      type: 'local',
      src: `/service-icons/${localIcon.file}`,
      color: localIcon.color,
      bgColor: getBgColor(localIcon.color),
      title: name,
      slug,
    };
  }
  
  // 1. Check SVGL known icons (full color)
  const svglIcon = SVGL_ICONS[slug] || SVGL_ICONS[name.toLowerCase()];
  if (svglIcon) {
    // Handle light/dark variants
    let fileName: string;
    if (typeof svglIcon.file === 'string') {
      fileName = svglIcon.file;
    } else {
      // Use theme-appropriate variant
      fileName = theme === 'dark' ? svglIcon.file.dark : svglIcon.file.light;
    }
    
    return {
      type: 'svgl',
      src: `https://svgl.app/library/${fileName}.svg`,
      color: svglIcon.color,
      bgColor: getBgColor(svglIcon.color),
      title: name,
      slug: fileName,
    };
  }
  
  // 2. Try Simple Icons
  const simpleIcon = getSimpleIconData(name);
  if (simpleIcon) {
    const color = `#${simpleIcon.hex}`;
    return {
      type: 'simple-icons',
      src: `https://cdn.simpleicons.org/${simpleIcon.slug}/${simpleIcon.hex}`,
      color,
      bgColor: getBgColor(color),
      title: simpleIcon.title,
      slug: simpleIcon.slug,
    };
  }
  
  // 3. Fallback to Lucide with category inference
  const category = inferCategory(name);
  const fallback = CATEGORY_FALLBACKS[category] || CATEGORY_FALLBACKS['default'];
  
  return {
    type: 'lucide',
    src: fallback.icon, // This is the Lucide icon name
    color: fallback.color,
    bgColor: getBgColor(fallback.color),
    title: name,
    slug,
  };
}

/**
 * Get multiple service icons at once
 */
export function getServiceIcons(names: string[]): Record<string, ServiceIcon> {
  const result: Record<string, ServiceIcon> = {};
  for (const name of names) {
    result[name] = getServiceIcon(name);
  }
  return result;
}

/**
 * Search for services by name (useful for autocomplete)
 */
export function searchServices(query: string, limit: number = 10): ServiceIcon[] {
  const results: ServiceIcon[] = [];
  const queryLower = query.toLowerCase();
  
  // Search SVGL icons first
  for (const [name, data] of Object.entries(SVGL_ICONS)) {
    const fileMatch = typeof data.file === 'string' 
      ? data.file.includes(queryLower)
      : (data.file.light.includes(queryLower) || data.file.dark.includes(queryLower));
    
    if (name.includes(queryLower) || fileMatch) {
      results.push(getServiceIcon(name));
      if (results.length >= limit) return results;
    }
  }
  
  // Search Simple Icons
  for (const [key, icon] of Object.entries(simpleIcons)) {
    if (key === 'default') continue;
    
    const iconData = icon as { slug?: string; title?: string };
    if (!iconData.slug) continue;
    
    if (
      iconData.slug.includes(queryLower) ||
      iconData.title?.toLowerCase().includes(queryLower)
    ) {
      // Avoid duplicates
      if (!results.find(r => r.slug === iconData.slug)) {
        results.push(getServiceIcon(iconData.title || iconData.slug));
        if (results.length >= limit) return results;
      }
    }
  }
  
  return results;
}

/**
 * Check if a service icon exists (not fallback)
 */
export function hasServiceIcon(name: string): boolean {
  const icon = getServiceIcon(name);
  return icon.type !== 'lucide';
}

// ============================================
// REACT COMPONENT HELPER
// ============================================

/**
 * Get props for rendering a service icon in React
 * 
 * Usage:
 *   const iconProps = getServiceIconProps('stripe');
 *   // For svgl/simple-icons: <img {...iconProps} />
 *   // For lucide: <LucideIcon name={iconProps.lucideIcon} style={iconProps.style} />
 */
export function getServiceIconProps(name: string, size: number = 24) {
  const icon = getServiceIcon(name);
  
  if (icon.type === 'lucide') {
    return {
      isLucide: true,
      lucideIcon: icon.src,
      style: { color: icon.color },
      size,
      title: icon.title,
      color: icon.color,
      bgColor: icon.bgColor,
    };
  }
  
  return {
    isLucide: false,
    src: icon.src,
    alt: icon.title,
    width: size,
    height: size,
    style: { objectFit: 'contain' as const },
    title: icon.title,
    color: icon.color,
    bgColor: icon.bgColor,
  };
}

