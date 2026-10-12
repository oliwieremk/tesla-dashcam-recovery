import Cocoa

final class Launcher: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var process: Process?
    var child: Process?
    var status: NSTextField!
    var logURL: URL!
    func text(_ pl: String, _ en: String) -> String {
        let environment = ProcessInfo.processInfo.environment
        let directory = environment["TESLARECOVER_DATA_DIR"] ?? NSHomeDirectory() + "/Library/Application Support/TeslaRecover"
        if let data = FileManager.default.contents(atPath: directory + "/settings.json"),
           let settings = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           settings["language"] as? String == "en" { return en }
        return pl
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let bundle = Bundle.main
        guard let source = bundle.resourceURL?.appendingPathComponent("app") else { NSApp.terminate(nil); return }
        let env = ProcessInfo.processInfo.environment
        let runtime = URL(fileURLWithPath: env["TESLARECOVER_RUNTIME_ROOT"] ?? NSHomeDirectory() + "/Library/Application Support/TeslaRecover")
        try? FileManager.default.createDirectory(at: runtime, withIntermediateDirectories: true)
        logURL = runtime.appendingPathComponent("startup.log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let log = try? FileHandle(forWritingTo: logURL)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 480, height: 220), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Tesla Recovery"
        window.center()
        let title = NSTextField(labelWithString: text("Przygotowujemy aplikację.", "Preparing the app."))
        title.font = .systemFont(ofSize: 22, weight: .semibold)
        title.frame = NSRect(x: 28, y: 145, width: 424, height: 30)
        status = NSTextField(wrappingLabelWithString: text("Pierwsze uruchomienie pobierze Python i potrzebne składniki. Kolejne starty są szybsze. Wymagane połączenie z internetem.", "The first launch downloads Python and required components. Later launches are faster. An internet connection is required."))
        status.textColor = .secondaryLabelColor
        status.frame = NSRect(x: 28, y: 65, width: 424, height: 66)
        let progress = NSProgressIndicator(frame: NSRect(x: 28, y: 35, width: 424, height: 15))
        progress.style = .bar; progress.isIndeterminate = true; progress.startAnimation(nil)
        window.contentView?.addSubview(title); window.contentView?.addSubview(status); window.contentView?.addSubview(progress)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        let prepare = Process()
        prepare.executableURL = URL(fileURLWithPath: "/bin/bash")
        prepare.arguments = [source.appendingPathComponent("macos/bootstrap.sh").path]
        prepare.standardOutput = log; prepare.standardError = log
        prepare.environment = env
        prepare.terminationHandler = { [weak self] task in
            DispatchQueue.main.async {
                guard let self = self else { return }
                try? log?.close()
                if task.terminationStatus != 0 { self.failed(self.text("Nie udało się pobrać lub przygotować składników. Sprawdź internet i spróbuj ponownie.", "Could not download or prepare the components. Check your internet connection and try again.")); return }
                let python = Process()
                python.executableURL = runtime.appendingPathComponent("runtime/bin/python")
                python.arguments = ["-B", source.appendingPathComponent("mac_launch.py").path] + Array(CommandLine.arguments.dropFirst())
                python.currentDirectoryURL = source
                var pythonEnv = env; pythonEnv["PYTHONDONTWRITEBYTECODE"] = "1"
                python.environment = pythonEnv
                let runLog = try? FileHandle(forWritingTo: self.logURL); _ = try? runLog?.seekToEnd()
                python.standardOutput = runLog; python.standardError = runLog
                python.terminationHandler = { [weak self] done in
                    DispatchQueue.main.async {
                        try? runLog?.close()
                        if done.terminationStatus != 0 { self?.failed(self?.text("Aplikacja zakończyła pracę z błędem. Szczegóły zapisano w dzienniku uruchomienia.", "The app exited with an error. Details are in the startup log.") ?? "The app exited with an error. Details are in the startup log.") }
                        else { NSApp.terminate(nil) }
                    }
                }
                self.child = python
                do { try python.run(); self.window.orderOut(nil); NSApp.setActivationPolicy(.accessory) }
                catch { self.failed(self.text("Nie można uruchomić aplikacji: ", "Could not launch the app: ") + error.localizedDescription) }
            }
        }
        process = prepare
        do { try prepare.run() } catch { failed(text("Nie można rozpocząć instalacji: ", "Could not begin setup: ") + error.localizedDescription) }
    }
    func failed(_ message: String) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        window.orderOut(nil)
        let alert = NSAlert(); alert.messageText = text("Nie udało się uruchomić Tesla Recovery", "Could not start Tesla Recovery"); alert.informativeText = message
        alert.addButton(withTitle: text("Zamknij", "Close")); alert.addButton(withTitle: text("Otwórz dziennik", "Open log"))
        if alert.runModal() == .alertSecondButtonReturn { NSWorkspace.shared.open(logURL) }
        NSApp.terminate(nil)
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if let child = child, child.isRunning {
            let alert = NSAlert(); alert.messageText = text("Zamknij okno odzyskiwania", "Close the recovery window")
            alert.informativeText = text("Aby zakończyć odczyt i ponownie zamontować USB, zamknij główne okno aplikacji.", "Close the main app window to finish reading and remount the USB.")
            alert.addButton(withTitle: "OK"); alert.runModal()
            return .terminateCancel
        }
        if let process = process, process.isRunning { process.terminate() }
        return .terminateNow
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { return child == nil }
}
let application = NSApplication.shared
let delegate = Launcher()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
