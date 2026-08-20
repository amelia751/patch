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

  return (
    <main className="shell">
      <header className="brand">
        <p className="mark">Storygen</p>
        {story ? (
          <button type="button" className="reset" onClick={reset}>
            New story
          </button>
        ) : null}
      </header>

      {story ? (
        <section className="reading">
          {cover ? (
            <div className="cover">
              <img src={cover} alt="Story cover" />
            </div>
          ) : null}
          {title ? <h1 className="title">{title}</h1> : null}
          <article className="story">{story}</article>
        </section>
      ) : (
        <form className="compose" onSubmit={onSubmit}>
          <h1 className="headline">Write a prompt. Get a story.</h1>
          <p className="hint">Tab fills the example prompt.</p>
          <div className="field">
            <label htmlFor="prompt">Prompt</label>
            <textarea
              id="prompt"
              name="prompt"
              rows={6}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={onPromptKeyDown}
              placeholder="Enter your prompt here"
              required
            />
          </div>
          <button className="submit" type="submit" disabled={pending || !prompt.trim()}>
            {pending ? "Generating..." : "Generate story"}
          </button>
          {error ? <p className="error">{error}</p> : null}
        </form>
      )}
    </main>
  );
}
