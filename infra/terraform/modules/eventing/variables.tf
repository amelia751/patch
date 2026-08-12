variable "project_id" {
  description = "GCP project that owns the topics and subscriptions."
  type        = string
}

variable "name_prefix" {
  description = "Prefix applied to every topic and subscription name."
  type        = string
}

variable "topics" {
  description = "Unprefixed topic names from roadmap.md §10.4."
  type        = list(string)
}

variable "labels" {
  description = "Labels applied to every topic and subscription."
  type        = map(string)
  default     = {}
}

variable "ack_deadline_seconds" {
  description = "Subscriber ack deadline. Agent turns are slow; keep this generous."
  type        = number
  default     = 600
}

variable "message_retention" {
  description = "How long an unacknowledged message is retained."
  type        = string
  default     = "86400s"
}

variable "dead_letter_retention" {
  description = "How long undeliverable messages are held for operator review."
  type        = string
  default     = "604800s"
}

variable "max_delivery_attempts" {
  description = "Redeliveries before a message is dead-lettered."
  type        = number
  default     = 5

  validation {
    condition     = var.max_delivery_attempts >= 5 && var.max_delivery_attempts <= 100
    error_message = "Pub/Sub requires max_delivery_attempts between 5 and 100."
  }
}

variable "publisher_members" {
  description = "IAM members allowed to publish to every event topic."
  type        = list(string)
  default     = []
}

variable "subscriber_members" {
  description = "IAM members allowed to pull from every event subscription."
  type        = list(string)
  default     = []
}
