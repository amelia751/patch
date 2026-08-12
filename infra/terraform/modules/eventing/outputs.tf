output "topic_names" {
  description = "Map of logical topic name => fully qualified topic name."
  value       = { for k, t in google_pubsub_topic.events : k => t.name }
}

output "subscription_names" {
  description = "Map of logical topic name => pull subscription name."
  value       = { for k, s in google_pubsub_subscription.events : k => s.name }
}

output "dead_letter_topic" {
  description = "Shared dead-letter topic name."
  value       = google_pubsub_topic.dead_letter.name
}
