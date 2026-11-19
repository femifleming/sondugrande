// Lists the windows of a process: "id<TAB>width<TAB>height<TAB>title" per line.
// Used by make_shots.py to photograph Sondugrande's own windows and nothing else.
import CoreGraphics
import Foundation
let pid = Int32(CommandLine.arguments[1])!
let list = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as! [[String: Any]]
for w in list {
    guard let owner = w[kCGWindowOwnerPID as String] as? Int32, owner == pid else { continue }
    guard let layer = w[kCGWindowLayer as String] as? Int, layer == 0 else { continue }
    let b = w[kCGWindowBounds as String] as! [String: Double]
    let title = (w[kCGWindowName as String] as? String) ?? ""
    let onscreen = (w[kCGWindowIsOnscreen as String] as? Bool) ?? false
    if !onscreen { continue }
    print("\(w[kCGWindowNumber as String] as! Int)\t\(Int(b["Width"] ?? 0))\t\(Int(b["Height"] ?? 0))\t\(title)")
}
