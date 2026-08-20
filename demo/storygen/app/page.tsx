"use client";

import { FormEvent, useState } from "react";

export default function HomePage() {
  const [prompt, setPrompt] = useState("");
  const [story, setStory] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setStory("");

    try {
      const response = await fetch("/api/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const payload = (await response.json()) as { story?: string; error?: string };
      if (!response.ok) {
        throw new Error(payload.error ?? "Story generation failed");
      }
      setStory(payload.story ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Story generation failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">Storygen</p>
        <h1>Write a prompt. Get a story.</h1>
        <p className="lede">
          A one-page writer that sends your idea to Gemini and prints the result.
        </p>
      </header>

      <form onSubmit={onSubmit}>
        <label htmlFor="prompt">Prompt</label>
        <textarea
          id="prompt"
          name="prompt"
          rows={6}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="A lighthouse keeper who receives letters from the future"
          required
        />
        <button type="submit" disabled={pending || !prompt.trim()}>
          {pending ? "Writing…" : "Generate story"}
        </button>
      </form>

      {error ? <p className="error">{error}</p> : null}
      {story ? <article>{story}</article> : null}
    </main>
  );
}
