"use client";

import Link from "next/link";
import { Waypoints, ArrowRight, Github, Sparkles, Cloud, Database, Code2, Network, Zap, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function HubPage() {
  return (
    <div className="min-h-screen bg-[var(--bg-secondary)] transition-colors">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-[var(--bg-primary)]/80 backdrop-blur-lg border-b border-[var(--border-color)]">
        <div className="max-w-6xl mx-auto px-6 py-3">
          <div className="flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 group">
              <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center transition-all group-hover:scale-105">
                <Waypoints className="h-5 w-5 text-white" />
              </div>
              <span className="text-base font-semibold text-[var(--text-primary)]">PatchAPI</span>
            </Link>

            <Link href="/">
              <Button className="bg-primary hover:bg-primary-hover text-primary-foreground text-xs px-4 h-8">
                Open App
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="px-6 pt-20 pb-16">
        <div className="max-w-6xl mx-auto">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] mb-6">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              <span className="text-xs text-[var(--text-secondary)]">AI-Powered Architecture Design</span>
            </div>

            <h1 className="text-5xl md:text-6xl font-bold text-[var(--text-primary)] mb-4 leading-tight">
              Design cloud architecture
              <span className="block text-primary mt-2">
                through conversation
              </span>
            </h1>

            <p className="text-base text-[var(--text-secondary)] mb-8 max-w-2xl mx-auto">
              Import your frontend, chat with AI, and get production-ready AWS infrastructure.
              Lambda, DynamoDB, API Gateway, and more.
            </p>

            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Link href="/">
                <Button className="bg-primary hover:bg-primary-hover text-primary-foreground px-6 h-10">
                  Start Building
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <Button
                variant="outline"
                className="bg-transparent border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] px-6 h-10"
              >
                <Github className="mr-2 h-4 w-4" />
                Connect GitHub
              </Button>
            </div>
          </div>

          {/* Demo Preview */}
          <div className="relative max-w-4xl mx-auto">
            <div className="rounded-xl overflow-hidden border border-[var(--border-color)] shadow-2xl bg-[var(--bg-primary)]">
              <div className="bg-[var(--bg-secondary)] border-b border-[var(--border-color)] px-4 py-2 flex items-center gap-2">
                <div className="flex gap-1.5">
                  <div className="h-2.5 w-2.5 rounded-full bg-red-500/80"></div>
                  <div className="h-2.5 w-2.5 rounded-full bg-yellow-500/80"></div>
                  <div className="h-2.5 w-2.5 rounded-full bg-green-500/80"></div>
                </div>
                <div className="flex-1 text-center text-xs text-[var(--text-tertiary)] font-mono">
                  System Architecture
                </div>
              </div>
              <div className="p-6 bg-[var(--bg-primary)]">
                <div className="grid grid-cols-3 gap-3 mb-4">
                  {[
                    { icon: Cloud, label: "API Gateway", color: "bg-blue-500/10 border-blue-500/20" },
                    { icon: Code2, label: "Lambda", color: "bg-orange-500/10 border-orange-500/20" },
                    { icon: Database, label: "DynamoDB", color: "bg-purple-500/10 border-purple-500/20" },
                  ].map((item, i) => (
                    <div key={i} className={`${item.color} rounded-lg p-3 border`}>
                      <item.icon className="h-6 w-6 text-[var(--text-secondary)] mb-1" />
                      <div className="text-xs font-medium text-[var(--text-primary)]">{item.label}</div>
                    </div>
                  ))}
                </div>
                <div className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border-color)]">
                  <div className="text-xs text-[var(--text-secondary)] mb-2">
                    "Build a serverless API with authentication"
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse"></div>
                    <div className="text-xs shimmer-text">Designing architecture</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="px-6 py-16 bg-[var(--bg-primary)]">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-[var(--text-primary)] mb-3">
              Everything you need
            </h2>
            <p className="text-sm text-[var(--text-secondary)] max-w-2xl mx-auto">
              From provider deprecations to verified pull requests, PatchAPI
              finds the affected code and stops at human review.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              {
                icon: Network,
                title: "Infrastructure Graph",
                description: "Visualize AWS services with interactive graphs and dependencies.",
              },
              {
                icon: Code2,
                title: "API Design",
                description: "Generate REST API routes and integration patterns automatically.",
              },
              {
                icon: Database,
                title: "Database Schema",
                description: "Design schemas with relationships, indexes, and constraints.",
              },
              {
                icon: Lock,
                title: "Security",
                description: "Built-in IAM policies and compliance guardrails.",
              },
              {
                icon: Zap,
                title: "Multi-Environment",
                description: "Deploy to dev, staging, and production environments.",
              },
              {
                icon: Cloud,
                title: "AWS Native",
                description: "Optimized for AWS with cost-efficient architectures.",
              },
            ].map((feature, i) => (
              <div
                key={i}
                className="bg-[var(--bg-secondary)] rounded-lg p-5 border border-[var(--border-color)] hover:border-primary transition-all group"
              >
                <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center mb-3 group-hover:bg-primary/20 transition-colors">
                  <feature.icon className="h-5 w-5 text-primary" />
                </div>
                <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1.5">
                  {feature.title}
                </h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="px-6 py-16">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-[var(--text-primary)] mb-3">
              How it works
            </h2>
            <p className="text-sm text-[var(--text-secondary)] max-w-2xl mx-auto">
              Four steps from frontend to production-ready backend
            </p>
          </div>

          <div className="grid md:grid-cols-4 gap-6">
            {[
              {
                step: "01",
                title: "Import Frontend",
                description: "Connect your GitHub repository. We analyze your React/Next.js code.",
              },
              {
                step: "02",
                title: "Extract Contracts",
                description: "We detect API calls and data needs from your components.",
              },
              {
                step: "03",
                title: "Chat to Design",
                description: "Tell AI what you need. We design Lambda, DynamoDB, and more.",
              },
              {
                step: "04",
                title: "Deploy",
                description: "Get infrastructure code. One click to deploy to AWS.",
              },
            ].map((item, i) => (
              <div key={i} className="relative">
                <div className="text-4xl font-bold text-[var(--text-tertiary)]/30 mb-3">
                  {item.step}
                </div>
                <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
                  {item.title}
                </h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="px-6 py-16 bg-[var(--bg-primary)]">
        <div className="max-w-3xl mx-auto text-center">
          <div className="rounded-xl bg-primary/10 border border-primary/20 p-12">
            <h2 className="text-3xl font-bold text-[var(--text-primary)] mb-3">
              Ready to build?
            </h2>
            <p className="text-sm text-[var(--text-secondary)] mb-6 max-w-xl mx-auto">
              Start designing your cloud architecture with AI. Import your frontend and chat your way to production.
            </p>
            <Link href="/">
              <Button className="bg-primary hover:bg-primary-hover text-primary-foreground px-8 h-10">
                Open PatchAPI
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="px-6 py-8 border-t border-[var(--border-color)] bg-[var(--bg-primary)]">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="h-6 w-6 rounded-lg bg-primary flex items-center justify-center">
                <Waypoints className="h-4 w-4 text-white" />
              </div>
              <span className="text-sm font-semibold text-[var(--text-primary)]">PatchAPI</span>
            </div>
            <div className="flex items-center gap-6">
              <Link href="#" className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
                Terms
              </Link>
              <Link href="#" className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
                Privacy
              </Link>
              <Link href="#" className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
                GitHub
              </Link>
            </div>
            <div className="text-xs text-[var(--text-tertiary)]">
              © 2026 PatchAPI
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
