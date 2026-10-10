import CoreImage
import CoreVideo
import ImageIO

struct EncodedJPEG {
    let data: Data
    let width: Int
    let height: Int
}

/// ARFrame.capturedImage (YCbCr, sensor orientation) -> JPEG, downscaled so the long side <= longSide.
/// No rotation: Python rotates using device_orientation.
final class FrameEncoder {
    private let context = CIContext(options: [.cacheIntermediates: false])
    private let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!

    func jpeg(_ pixelBuffer: CVPixelBuffer, longSide: Int, quality: Double) -> EncodedJPEG? {
        var image = CIImage(cvPixelBuffer: pixelBuffer)
        let scale = min(1, CGFloat(longSide) / max(image.extent.width, image.extent.height))
        if scale < 1 {
            image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        }
        let options = [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: quality]
        guard let data = context.jpegRepresentation(of: image, colorSpace: colorSpace, options: options),
              let (width, height) = Self.pixelSize(of: data)
        else { return nil }
        return EncodedJPEG(data: data, width: width, height: height)
    }

    /// Read the real pixel size from the JPEG so the header can never disagree with the payload.
    private static func pixelSize(of data: Data) -> (Int, Int)? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = props[kCGImagePropertyPixelWidth] as? Int,
              let height = props[kCGImagePropertyPixelHeight] as? Int
        else { return nil }
        return (width, height)
    }
}
