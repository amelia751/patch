"use client";

import { FormEvent, KeyboardEvent, useState } from "react";

const EXAMPLE_PROMPT = "A lighthouse keeper who receives letters from the future";

export default function HomePage() {
  const [prompt, setPrompt] = useState("");
  const [story, setStory] = useState("");
  const [title, setTitle] = useState("");
  const [cover, setCover] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  function onPromptKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Tab" || prompt.trim()) {
      return;
    }
    event.preventDefault();
    setPrompt(EXAMPLE_PROMPT);
  }

  function reset() {
    setStory("");
    setTitle("");
    setCover("");
    setError("");
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setStory("");
    setTitle("");
    setCover("");

    try {
      const response = await fetch("/api/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const payload = (await response.json()) as {
        story?: string;
        title?: string;
        cover?: string | null;
        error?: string;
      };
      if (!response.ok) {
        throw new Error(payload.error ?? "Failed to generate story.");
      }
      setStory(payload.story ?? "");
      setTitle(payload.title ?? "");
      setCover(payload.cover ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate story.");
    } finally {
      setPending(false);
    }
  }

  if (story) {
    return (
      <main className="result">
        <button type="button" className="reset" onClick={reset}>
          New story
        </button>
        <div className="hero">
          {cover ? (
            <div className="cover">
              <img src={cover} alt="Story cover" />
            </div>
          ) : null}
          {title ? (
            <div className="names">
              <h2 className="learn-name">{title}</h2>
            </div>
          ) : null}
        </div>
        <article>{story}</article>
      </main>
    );
  }

  return (
    <main>
      <form className="compose" onSubmit={onSubmit}>
        <h1 className="pill title-pill">Story Generator</h1>
        <textarea
          id="prompt"
          name="prompt"
          rows={4}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          onKeyDown={onPromptKeyDown}
          placeholder="Enter your prompt here"
          required
        />
        <button className="pill action-pill" type="submit" disabled={pending || !prompt.trim()}>
          {pending ? "Generating..." : "Generate Story"}
        </button>
        {error ? <p className="error">{error}</p> : null}
      </form>
    </main>
  );
}
