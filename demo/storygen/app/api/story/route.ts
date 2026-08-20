import { generateCover, generateStory, generateTitle } from "@/lib/gemini";

type CallResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: string };

async function settle<T>(work: Promise<T>): Promise<CallResult<T>> {
  try {
    return { ok: true, value: await work };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : "Request failed",
    };
  }
}

export async function POST(request: Request): Promise<Response> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return Response.json({ error: "GEMINI_API_KEY is not set" }, { status: 500 });
  }

  let prompt = "";
  try {
    const body = (await request.json()) as { prompt?: unknown };
    prompt = typeof body.prompt === "string" ? body.prompt.trim() : "";
  } catch {
    return Response.json({ error: "Request body must be JSON" }, { status: 400 });
  }

  if (!prompt) {
    return Response.json({ error: "Enter your prompt here" }, { status: 400 });
  }

  // Cover uses the prompt, not the story, so a dead text model cannot hide
  // the retired Imagen call.
  const [storyResult, coverResult] = await Promise.all([
    settle(generateStory(prompt, apiKey)),
    settle(generateCover(prompt, apiKey)),
  ]);

  const errors: { story?: string; cover?: string } = {};
  if (!storyResult.ok) {
    errors.story = storyResult.error;
  }
  if (!coverResult.ok) {
    errors.cover = coverResult.error;
  }

  if (!storyResult.ok) {
    return Response.json({ errors }, { status: 502 });
  }

  const titleResult = await settle(generateTitle(storyResult.value, apiKey));
  if (!titleResult.ok) {
    errors.story = titleResult.error;
  }

  return Response.json({
    story: storyResult.value,
    title: titleResult.ok ? titleResult.value : "",
    cover: coverResult.ok ? coverResult.value : null,
    errors: Object.keys(errors).length > 0 ? errors : undefined,
  });
}
