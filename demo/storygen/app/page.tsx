"use client";

import { FormEvent, KeyboardEvent, useState } from "react";

const EXAMPLE_PROMPT = "A lighthouse keeper who receives letters from the future";

type Errors = {
  story?: string;
  cover?: string;
};

export default function HomePage() {
  const [prompt, setPrompt] = useState("");
  const [story, setStory] = useState("");
  const [title, setTitle] = useState("");
  const [cover, setCover] = useState("");
  const [errors, setErrors] = useState<Errors>({});
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
    setErrors({});
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setErrors({});
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
        errors?: Errors;
      };
      const nextErrors: Errors = { ...payload.errors };
      if (payload.error && !nextErrors.story) {
        nextErrors.story = payload.error;
      }
      setErrors(nextErrors);
      if (!response.ok) {
        return;
      }
      setStory(payload.story ?? "");
      setTitle(payload.title ?? "");
      setCover(payload.cover ?? "");
    } catch (err) {
      setErrors({
        story: err instanceof Error ? err.message : "Failed to generate story.",
      });
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
          {title ? <h2 className="learn-name">{title}</h2> : null}
        </div>
        <ErrorList errors={errors} />
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
        <ErrorList errors={errors} />
      </form>
    </main>
  );
}

function ErrorList({ errors }: { errors: Errors }) {
  if (!errors.story && !errors.cover) {
    return null;
  }
  return (
    <dl className="errors">
      {errors.story ? (
        <div className="error">
          <dt>Story · gemini-2.0-flash</dt>
          <dd>{errors.story}</dd>
        </div>
      ) : null}
      {errors.cover ? (
        <div className="error">
          <dt>Cover · imagen-4.0-generate-001</dt>
          <dd>{errors.cover}</dd>
        </div>
      ) : null}
    </dl>
  );
}
