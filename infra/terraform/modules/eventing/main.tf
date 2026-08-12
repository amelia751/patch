# Durable event flow between the control plane and the ADK agents
# (roadmap.md §10.4). Each topic gets a pull subscription and a shared
# dead-letter topic.
#
# Messages carry run IDs and GCS URIs only, never repository source. That is a
# code-side contract, but the retention settings here assume it: a topic that
# leaked source would be holding customer code for `message_retention` days.

resource "google_pubsub_topic" "dead_letter" {
  project = var.project_id
  name    = "${var.name_prefix}-dead-letter"

  message_retention_duration = var.message_retention
  labels                     = var.labels
}

resource "google_pubsub_subscription" "dead_letter" {
  project = var.project_id
  name    = "${var.name_prefix}-dead-letter-sub"
  topic   = google_pubsub_topic.dead_letter.id

  # Undeliverable events are an operator signal; hold them long enough for a
  # human to read the run that produced them.
  message_retention_duration = var.dead_letter_retention
  labels                     = var.labels
}

resource "google_pubsub_topic" "events" {
  for_each = toset(var.topics)

  project = var.project_id
  name    = "${var.name_prefix}-${each.value}"

  message_retention_duration = var.message_retention
  labels                     = var.labels
}

resource "google_pubsub_subscription" "events" {
  for_each = google_pubsub_topic.events

  project = var.project_id
  name    = "${each.value.name}-sub"
  topic   = each.value.id

  ack_deadline_seconds       = var.ack_deadline_seconds
  message_retention_duration = var.message_retention
  labels                     = var.labels

  # Fail closed: a poisoned provider event must stop after a bounded number of
  # redeliveries instead of driving the agent fleet in a loop.
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = var.max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

# Pub/Sub itself needs permission to forward into and drain from the topics it
# manages a dead-letter policy for.
data "google_project" "this" {
  project_id = var.project_id
}

locals {
  pubsub_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.dead_letter.name
  role    = "roles/pubsub.publisher"
  member  = local.pubsub_agent
}

resource "google_pubsub_subscription_iam_member" "dead_letter_subscriber" {
  for_each = google_pubsub_subscription.events

  project      = var.project_id
  subscription = each.value.name
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_agent
}

resource "google_pubsub_topic_iam_member" "publishers" {
  for_each = {
    for pair in setproduct(var.topics, var.publisher_members) :
    "${pair[0]}:${pair[1]}" => { topic = pair[0], member = pair[1] }
  }

  project = var.project_id
  topic   = google_pubsub_topic.events[each.value.topic].name
  role    = "roles/pubsub.publisher"
  member  = each.value.member
}

resource "google_pubsub_subscription_iam_member" "subscribers" {
  for_each = {
    for pair in setproduct(var.topics, var.subscriber_members) :
    "${pair[0]}:${pair[1]}" => { topic = pair[0], member = pair[1] }
  }

  project      = var.project_id
  subscription = google_pubsub_subscription.events[each.value.topic].name
  role         = "roles/pubsub.subscriber"
  member       = each.value.member
}
