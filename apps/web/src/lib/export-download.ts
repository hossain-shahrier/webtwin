/** Clipboard size limit — above this we download instead of copying. */
export const CLIPBOARD_MAX_BYTES = 200_000;

function byteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}

function downloadBlob(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function copyWithClipboardApi(text: string): Promise<boolean> {
  if (!navigator.clipboard?.writeText) {
    return false;
  }
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function copyWithExecCommand(text: string): boolean {
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.top = '0';
    textarea.style.left = '0';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const copied = document.execCommand('copy');
    textarea.remove();
    return copied;
  } catch {
    return false;
  }
}

export async function copyOrDownloadText(options: {
  text: string;
  filename: string;
  mime?: string;
  clipboardMaxBytes?: number;
}): Promise<'copied' | 'downloaded'> {
  const mime = options.mime ?? 'text/plain;charset=utf-8';
  const maxBytes = options.clipboardMaxBytes ?? CLIPBOARD_MAX_BYTES;
  const size = byteLength(options.text);

  if (size > maxBytes) {
    downloadBlob(options.text, options.filename, mime);
    return 'downloaded';
  }

  if (await copyWithClipboardApi(options.text)) {
    return 'copied';
  }
  if (copyWithExecCommand(options.text)) {
    return 'copied';
  }

  downloadBlob(options.text, options.filename, mime);
  return 'downloaded';
}

export function exportFilename(
  investigationId: string,
  kind: 'ai-context' | 'cursor-context' | 'clone-spec',
  extension: 'md' | 'json',
): string {
  const shortId = investigationId.slice(0, 8);
  return `webtwin-${kind}-${shortId}.${extension}`;
}

export function exportResultMessage(
  result: 'copied' | 'downloaded',
  label: string,
  filename: string,
): string {
  if (result === 'copied') {
    return `Copied ${label} to clipboard`;
  }
  return `Downloaded ${label} as ${filename} (clipboard unavailable or export too large)`;
}
