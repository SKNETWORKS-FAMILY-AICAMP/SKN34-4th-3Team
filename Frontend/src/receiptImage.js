// 영수증 업로드 전 이미지 축소. 휴대폰 원본 사진은 서버 상한(4MB)을 넘기 쉬워서
// 긴 변 2000px JPEG로 줄여 올린다. 서버 OCR도 어차피 2000px로 줄여 읽으므로 인식률은 그대로다.

export const MAX_RECEIPT_BYTES = 4 * 1024 * 1024;
export const MAX_RECEIPT_SIDE = 2000;

/** 비율을 지키며 긴 변이 max 이하가 되는 크기. 이미 작으면 그대로 돌려준다. */
export function fitWithin(width, height, max = MAX_RECEIPT_SIDE) {
  const long = Math.max(width, height);
  if (long <= max) return { width, height };
  const scale = max / long;
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/**
 * 올릴 파일을 돌려준다. 작은 이미지는 원본 그대로, 큰 이미지는 줄인 JPEG.
 * 4MB 안으로 만들 수 없으면 null.
 */
export async function prepareReceiptImage(file) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    // 브라우저가 못 여는 이미지는 줄일 수 없다. 상한 안이면 서버 판단에 맡긴다.
    return file.size <= MAX_RECEIPT_BYTES ? file : null;
  }
  try {
    if (Math.max(bitmap.width, bitmap.height) <= MAX_RECEIPT_SIDE && file.size <= MAX_RECEIPT_BYTES) return file;
    const { width, height } = fitWithin(bitmap.width, bitmap.height);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    // PNG 투명 영역이 JPEG에서 검게 나오지 않도록 흰 바탕을 깐다.
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(bitmap, 0, 0, width, height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
    if (!blob || blob.size > MAX_RECEIPT_BYTES) return null;
    const name = (file.name || 'receipt').replace(/\.[^.]*$/, '') + '.jpg';
    return new File([blob], name, { type: 'image/jpeg' });
  } finally {
    bitmap.close();
  }
}
