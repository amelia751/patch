/**
 * Persona Icon Registry
 * 
 * Maps user personas/roles to appropriate Lucide icons.
 * Supports exact match, keyword match, and category inference.
 */

import {
  User,
  Shield,
  UserX,
  Heart,
  Stethoscope,
  Syringe,
  Scale,
  Gavel,
  Briefcase,
  GraduationCap,
  BookOpen,
  ShoppingCart,
  Store,
  Package,
  Crown,
  Star,
  UserCog,
  Users,
  Building2,
  Headphones,
  Wrench,
  Eye,
  PenTool,
  Megaphone,
  DollarSign,
  Truck,
  type LucideIcon,
} from "lucide-react";

// Icon registry with categories
const PERSONA_ICONS: Record<string, LucideIcon> = {
  // Generic roles
  user: User,
  customer: User,
  member: User,
  subscriber: User,
  guest: UserX,
  visitor: UserX,
  anonymous: UserX,
  
  // Admin & Management
  admin: Shield,
  administrator: Shield,
  superadmin: Shield,
  moderator: UserCog,
  manager: UserCog,
  owner: Crown,
  
  // Healthcare
  patient: Heart,
  doctor: Stethoscope,
  physician: Stethoscope,
  nurse: Syringe,
  caregiver: Heart,
  therapist: Heart,
  
  // Legal
  lawyer: Scale,
  attorney: Scale,
  judge: Gavel,
  client: Briefcase,
  paralegal: Briefcase,
  
  // Education
  student: GraduationCap,
  teacher: BookOpen,
  professor: BookOpen,
  instructor: BookOpen,
  tutor: BookOpen,
  
  // E-commerce
  buyer: ShoppingCart,
  seller: Store,
  vendor: Package,
  merchant: Store,
  supplier: Truck,
  
  // Business
  employee: Users,
  staff: Users,
  team: Users,
  company: Building2,
  enterprise: Building2,
  organization: Building2,
  
  // Support & Service
  support: Headphones,
  agent: Headphones,
  representative: Headphones,
  technician: Wrench,
  
  // Content & Media
  viewer: Eye,
  reader: Eye,
  author: PenTool,
  editor: PenTool,
  creator: PenTool,
  writer: PenTool,
  
  // Marketing & Sales
  marketer: Megaphone,
  advertiser: Megaphone,
  salesperson: DollarSign,
  
  // Premium tiers
  premium: Star,
  vip: Crown,
  pro: Star,
  
  // Default
  default: User,
};

// Color mapping for persona types
const PERSONA_COLORS: Record<string, string> = {
  // Admin types - red/orange
  admin: "#E53935",
  administrator: "#E53935",
  superadmin: "#C62828",
  moderator: "#FF7043",
  
  // Users - blue
  user: "#1E88E5",
  customer: "#1E88E5",
  member: "#42A5F5",
  subscriber: "#42A5F5",
  
  // Guest - gray
  guest: "#78909C",
  visitor: "#78909C",
  anonymous: "#90A4AE",
  
  // Healthcare - green/teal
  patient: "#26A69A",
  doctor: "#00897B",
  nurse: "#4DB6AC",
  
  // Legal - purple
  lawyer: "#7E57C2",
  judge: "#5E35B1",
  client: "#9575CD",
  
  // Education - indigo
  student: "#5C6BC0",
  teacher: "#3F51B5",
  
  // E-commerce - amber/orange
  buyer: "#FF8F00",
  seller: "#F57C00",
  vendor: "#EF6C00",
  
  // Premium - gold
  premium: "#FFB300",
  vip: "#FFA000",
  
  // Default
  default: "#5294CF",
};

/**
 * Get the icon component for a persona type
 */
export function getPersonaIcon(personaType: string): LucideIcon {
  const normalized = personaType.toLowerCase().replace(/[^a-z]/g, "");
  
  // Direct match
  if (PERSONA_ICONS[normalized]) {
    return PERSONA_ICONS[normalized];
  }
  
  // Partial/keyword match
  for (const [key, icon] of Object.entries(PERSONA_ICONS)) {
    if (normalized.includes(key) || key.includes(normalized)) {
      return icon;
    }
  }
  
  return PERSONA_ICONS.default;
}

/**
 * Get the color for a persona type
 */
export function getPersonaColor(personaType: string): string {
  const normalized = personaType.toLowerCase().replace(/[^a-z]/g, "");
  
  // Direct match
  if (PERSONA_COLORS[normalized]) {
    return PERSONA_COLORS[normalized];
  }
  
  // Partial match
  for (const [key, color] of Object.entries(PERSONA_COLORS)) {
    if (normalized.includes(key) || key.includes(normalized)) {
      return color;
    }
  }
  
  return PERSONA_COLORS.default;
}

/**
 * Get both icon and color for a persona
 */
export function getPersonaStyle(personaType: string): { icon: LucideIcon; color: string } {
  return {
    icon: getPersonaIcon(personaType),
    color: getPersonaColor(personaType),
  };
}

/**
 * Check if a service type is a persona
 */
export function isPersonaNode(service: string): boolean {
  return service.toLowerCase() === "persona" || service.toLowerCase() === "actor";
}

