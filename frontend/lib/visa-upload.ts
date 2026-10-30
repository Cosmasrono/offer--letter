const MAX_BYTES = 10 * 1024 * 1024;

export function validateVisaUpload(form: FormData): string | null {
  if (!["QA", "KW"].includes(String(form.get("country")))) return "Choose Qatar or Kuwait for a visa check.";
  const file = form.get("file");
  const offer = form.get("offerFile");
  for (const [label, value, optional] of [["visa", file, false], ["offer letter", offer, true]] as const) {
    if (optional && value === null) continue;
    if (!(value instanceof File) || value.size === 0) return `Choose a non-empty ${label} document.`;
    if (value.size > MAX_BYTES) return `The ${label} is too large. The limit is 10 MB per document.`;
    const allowed = label === "visa" ? ["pdf", "png", "jpg", "jpeg", "webp", "txt"] : ["pdf", "png", "jpg", "jpeg", "webp", "txt", "eml"];
    if (!allowed.includes(value.name.split(".").pop()?.toLowerCase() ?? "")) return `Unsupported ${label} file. Choose a PDF, image or text document.`;
  }
  return null;
}
