// Runtime call site. The model ID carries the Vertex routing prefix Egaki uses,
// which is why the scanner matches on substrings rather than whole tokens.
const IMAGE_MODEL = "vertex/imagen-4.0-generate-001";

export async function generateImage(prompt: string): Promise<Uint8Array> {
  const response = await fetch("https://example.invalid/generate", {
    method: "POST",
    body: JSON.stringify({ model: IMAGE_MODEL, prompt }),
  });
  return new Uint8Array(await response.arrayBuffer());
}
