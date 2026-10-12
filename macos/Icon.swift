import Cocoa

let destination = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) -> NSColor { NSColor(srgbRed: r, green: g, blue: b, alpha: 1) }
func drawIcon(size: Int, path: URL) throws {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let transform = NSAffineTransform(); transform.scale(by: CGFloat(size) / 1024); transform.concat()
    let background = NSBezierPath(roundedRect: NSRect(x: 80, y: 80, width: 864, height: 864), xRadius: 192, yRadius: 192)
    let gradient = NSGradient(starting: color(0.06, 0.10, 0.19), ending: color(0.12, 0.29, 0.50))!
    gradient.draw(in: background, angle: 90)
    color(0.25, 0.43, 0.66).setStroke(); background.lineWidth = 8; background.stroke()
    color(0.14, 0.24, 0.38).setFill()
    let hump = NSBezierPath(roundedRect: NSRect(x: 320, y: 675, width: 205, height: 75), xRadius: 28, yRadius: 28); hump.fill()
    color(0.54, 0.77, 1.0).setStroke(); hump.lineWidth = 14; hump.stroke()
    let camera = NSBezierPath(roundedRect: NSRect(x: 221, y: 335, width: 582, height: 375), xRadius: 66, yRadius: 66)
    color(0.12, 0.21, 0.34).setFill(); camera.fill()
    color(0.54, 0.77, 1.0).setStroke(); camera.lineWidth = 18; camera.stroke()
    let lens = NSBezierPath(ovalIn: NSRect(x: 390, y: 405, width: 244, height: 244))
    NSGradient(starting: color(0.14, 0.57, 0.96), ending: color(0.25, 0.86, 0.93))!.draw(in: lens, angle: 45)
    color(0.73, 0.90, 1.0).setStroke(); lens.lineWidth = 13; lens.stroke()
    let diamond = NSBezierPath(); diamond.move(to: NSPoint(x: 512, y: 592)); diamond.line(to: NSPoint(x: 577, y: 527)); diamond.line(to: NSPoint(x: 512, y: 462)); diamond.line(to: NSPoint(x: 447, y: 527)); diamond.close()
    color(0.08, 0.20, 0.36).setFill(); diamond.fill()
    let record = NSBezierPath(ovalIn: NSRect(x: 700, y: 624, width: 35, height: 35)); color(1, 0.36, 0.40).setFill(); record.fill()
    let recovery = NSBezierPath(); recovery.appendArc(withCenter: NSPoint(x: 512, y: 502), radius: 306, startAngle: 201, endAngle: 333, clockwise: false)
    recovery.lineWidth = 28; recovery.lineCapStyle = .round; color(0.31, 0.87, 0.94).setStroke(); recovery.stroke()
    let arrow = NSBezierPath(); arrow.move(to: NSPoint(x: 822, y: 410)); arrow.line(to: NSPoint(x: 827, y: 299)); arrow.line(to: NSPoint(x: 736, y: 345)); arrow.close(); color(0.31, 0.87, 0.94).setFill(); arrow.fill()
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using: .png, properties: [:])!.write(to: path)
}
for base in [16, 32, 128, 256, 512] {
    try drawIcon(size: base, path: destination.appendingPathComponent("icon_\(base)x\(base).png"))
    try drawIcon(size: base * 2, path: destination.appendingPathComponent("icon_\(base)x\(base)@2x.png"))
}
