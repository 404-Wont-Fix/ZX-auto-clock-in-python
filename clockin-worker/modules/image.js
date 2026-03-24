/**
 * 图片处理模块
 */

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

            return {
                success: true,
                data: {
                    buffer: imageBuffer,
                    contentType: imageResponse.headers.get('content-type') || 'image/jpeg',
                    fileName: `bing_${image.startdate}.jpg`
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
