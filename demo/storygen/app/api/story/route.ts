import { generateCover, generateStory, generateTitle } from "@/lib/gemini";

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

  try {
    const story = await generateStory(prompt, apiKey);
    const title = await generateTitle(story, apiKey);
    let cover: string | null = null;
    try {
      cover = await generateCover(story, apiKey);
    } catch {
      cover = null;
    }
    return Response.json({ story, title, cover });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Story generation failed";
    return Response.json({ error: message }, { status: 502 });
  }
}
