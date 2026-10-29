"use client";

/** 前端压缩：视觉模型对 512px 就够，压完省流量也省识别时间。 */
export type CompressedImage = {
  dataUrl: string;
  base64: string;
  mime: string;
  width: number;
  height: number;
  bytes: number;
};

const MAX_EDGE = 768;
const TARGET_BYTES = 420 * 1024;

export async function compressImage(file: File): Promise<CompressedImage> {
  return compressImageBlob(file);
}

export async function compressImageBlob(source: Blob): Promise<CompressedImage> {
  if (!source.type.startsWith("image/")) {
    throw new Error("请选择图片文件");
  }
  const bitmap = await createImageBitmap(source);
  try {
    let edge = MAX_EDGE;
    let quality = 0.82;
    let result = draw(bitmap, edge, quality);
    // 再压两档就够，避免在低端机上一直循环
    for (let i = 0; i < 2 && result.bytes > TARGET_BYTES; i += 1) {
      edge = Math.round(edge * 0.8);
      quality = Math.max(0.6, quality - 0.12);
      result = draw(bitmap, edge, quality);
    }
    return result;
  } finally {
    bitmap.close?.();
  }
}

function draw(bitmap: ImageBitmap, maxEdge: number, quality: number): CompressedImage {
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("浏览器不支持图片压缩");
  // 透明 PNG 转 JPEG 会变黑，先铺白底
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(bitmap, 0, 0, width, height);
  const dataUrl = canvas.toDataURL("image/jpeg", quality);
  const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
  return { dataUrl, base64, mime: "image/jpeg", width, height, bytes: Math.round((base64.length * 3) / 4) };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
