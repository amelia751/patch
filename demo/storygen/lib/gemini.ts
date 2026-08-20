export const MODEL = "gemini-2.0-flash";

const GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models";

type GeminiResponse = {
  candidates?: Array<{
    content?: { parts?: Array<{ text?: string }> };
  }>;
  error?: { message?: string };
};

export async function generateStory(prompt: string, apiKey: string): Promise<string> {
  const response = await fetch(
    `${GENERATE_URL}/${MODEL}:generateContent?key=${encodeURIComponent(apiKey)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [
          {
            parts: [
              {
                text: `Write a short story from this prompt. Keep it under 400 words.\n\n${prompt}`,
              },
            ],
          },
        ],
      }),
    },
  );

  const payload = (await response.json()) as GeminiResponse;
  if (!response.ok) {
    throw new Error(payload.error?.message ?? `Gemini request failed (${response.status})`);
  }

  const text = payload.candidates?.[0]?.content?.parts?.map((part) => part.text ?? "").join("");
  if (!text) {
    throw new Error("Gemini returned an empty story");
  }
  return text;
}
