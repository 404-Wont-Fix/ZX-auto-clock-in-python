/**
 * 图片处理模块
 */

/**
 * 通过文件头（magic bytes）识别真实图片格式。
 * 不信任响应的 Content-Type 头——ACG 图床经常返回与真实字节不一致的头
 * （例如把 WebP 标成 image/jpeg），这正是平台报
 * “文件内容与扩展名不匹配（图片验证失败）”的根因。
 *
 * @param {ArrayBuffer} buffer
 * @returns {{contentType: string, extension: string} | null}
 */
export function detectImageType(buffer) {
    const bytes = new Uint8Array(buffer);
    const len = bytes.length;
    if (!len) return null;

    // PNG: 89 50 4E 47
    if (len >= 4 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4E && bytes[3] === 0x47) {
        return { contentType: 'image/png', extension: 'png' };
    }
    // GIF: 47 49 46 38 (GIF8)
    if (len >= 4 && bytes[0] === 0x47 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x38) {
        return { contentType: 'image/gif', extension: 'gif' };
    }
    // WebP: "RIFF" .... "WEBP"
    if (len >= 12 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46
        && bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 && bytes[11] === 0x50) {
        return { contentType: 'image/webp', extension: 'webp' };
    }
    // JPEG: FF D8 FF
    if (len >= 3 && bytes[0] === 0xFF && bytes[1] === 0xD8 && bytes[2] === 0xFF) {
        return { contentType: 'image/jpeg', extension: 'jpg' };
    }
    // BMP: 42 4D (BM)
    if (len >= 2 && bytes[0] === 0x42 && bytes[1] === 0x4D) {
        return { contentType: 'image/bmp', extension: 'bmp' };
    }
    return null;
}

export async function getBingImage() {
    try {
        const response = await fetch('https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1&mkt=zh-CN');
        const data = await response.json();

        if (data && data.images && data.images.length > 0) {
            const image = data.images[0];
            const imageUrl = `https://www.bing.com${image.url}`;

            const imageResponse = await fetch(imageUrl);
            if (!imageResponse.ok) {
                throw new Error(`获取图片失败: ${imageResponse.status}`);
            }

            const imageBuffer = await imageResponse.arrayBuffer();
            const detected = detectImageType(imageBuffer);
            if (!detected) {
                throw new Error('必应图片格式无法识别');
            }

            return {
                success: true,
                data: {
                    buffer: imageBuffer,
                    contentType: detected.contentType,
                    fileName: `bing_${image.startdate}.${detected.extension}`
                }
            };
        } else {
            throw new Error('未找到必应图片');
        }
    } catch (error) {
        return {
            success: false,
            message: error.message,
            data: null
        };
    }
}
