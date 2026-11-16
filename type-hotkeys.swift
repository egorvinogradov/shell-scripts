// type-hotkeys: global hotkeys for the type-date / type-slug / type-hyphen shortcuts.
//
// WHY THIS EXISTS: keys set inside the Shortcuts app are "Services" keys. macOS fires them only
// when the front app has a Services menu. Some Electron apps (DeepSeek Harness) have no such menu,
// so the keys do nothing there. This listener registers real global hotkeys (Carbon), which work
// in every app, and runs the same ~/.local/bin scripts directly.
//
//   Shift+Ctrl+Option+Cmd+D -> ~/.local/bin/type-date
//   Shift+Ctrl+Option+Cmd+L -> ~/.local/bin/type-slug
//   Shift+Ctrl+Option+Cmd+K -> ~/.local/bin/type-hyphen
//
// BUILD + INSTALL:
//   swiftc -O type-hotkeys.swift -o ~/.local/bin/type-hotkeys \
//     -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker type-hotkeys.Info.plist
//   cp com.egor.type-hotkeys.plist ~/Library/LaunchAgents/
//   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.egor.type-hotkeys.plist
// REMOVE:
//   launchctl bootout gui/$(id -u)/com.egor.type-hotkeys; rm ~/Library/LaunchAgents/com.egor.type-hotkeys.plist
// First start: macOS asks for Accessibility for type-hotkeys. Switch it on in System Settings >
// Privacy & Security > Accessibility. Until then this program takes no keys (old Shortcuts keys still work).
// First key press may also ask to control "System Events". Click Allow.
// Debug: `kill -USR1 <pid>` runs type-slug as if L was pressed.

import AppKit
import Carbon

let shortcuts: [UInt32: (key: UInt32, name: String)] = [
    1: (UInt32(kVK_ANSI_D), "type-date"),
    2: (UInt32(kVK_ANSI_L), "type-slug"),
    3: (UInt32(kVK_ANSI_K), "type-hyphen"),
]
var busy = false

func run(_ name: String) {
    if busy { return }  // ignore key repeat while a run is in flight
    busy = true
    // Runs the script directly, so it types with THIS program's Accessibility permission.
    // (Going through "Shortcuts Events" does not work: scripts started that way get no Accessibility.)
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    p.arguments = [NSHomeDirectory() + "/.local/bin/" + name]
    p.terminationHandler = { proc in
        DispatchQueue.main.async { busy = false }
        if proc.terminationStatus != 0 { NSLog("type-hotkeys: \(name) failed, status \(proc.terminationStatus)") }
    }
    do { try p.run() } catch { busy = false; NSLog("type-hotkeys: \(error)") }
}

var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
InstallEventHandler(GetApplicationEventTarget(), { _, event, _ in
    var id = EventHotKeyID()
    GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                      nil, MemoryLayout<EventHotKeyID>.size, nil, &id)
    if let s = shortcuts[id.id] { run(s.name) }
    return noErr
}, 1, &spec, nil, nil)

// Keys are taken over ONLY once Accessibility is granted. Until then the old Shortcuts-app keys keep working.
let mods = UInt32(cmdKey | shiftKey | optionKey | controlKey)
var registered = false
func registerWhenTrusted() {
    if registered { return }
    if !AXIsProcessTrusted() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { registerWhenTrusted() }
        return
    }
    registered = true
    for (id, s) in shortcuts {
        var ref: EventHotKeyRef?
        let err = RegisterEventHotKey(s.key, mods, EventHotKeyID(signature: OSType(0x7479686B), id: id),
                                      GetApplicationEventTarget(), 0, &ref)
        NSLog("type-hotkeys: \(s.name) register status \(err)")
    }
}
// Shows the macOS dialog "type-hotkeys would like to control this computer" once, with a button to System Settings.
let trusted = AXIsProcessTrustedWithOptions(["AXTrustedCheckOptionPrompt": true] as CFDictionary)
NSLog("type-hotkeys: accessibility trusted = \(trusted)")
registerWhenTrusted()

signal(SIGUSR1, SIG_IGN)
let usr1 = DispatchSource.makeSignalSource(signal: SIGUSR1, queue: .main)
usr1.setEventHandler { run("type-slug") }
usr1.resume()

let app = NSApplication.shared
app.setActivationPolicy(.prohibited)  // no Dock icon, never takes focus
app.run()
