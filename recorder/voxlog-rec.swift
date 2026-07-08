// voxlog-rec — captura NATIVA (ScreenCaptureKit) do áudio do sistema + microfone,
// mistura em mono e escreve PCM f32le (48kHz) na stdout. Sem BlackHole / sem
// Multi-Output → a saída de som fica no dispositivo real (teclas de volume voltam).
//
// A stdout carrega SÓ o PCM (vai pro ffmpeg). Logs vão pra stderr.
// Encerra limpo em SIGTERM/SIGINT (fecha a stdout → ffmpeg finaliza o segmento).
//
// Requer macOS 15+ (mic via SCK). Precisa de permissão de Gravação de Tela + Microfone.
import ScreenCaptureKit
import AVFoundation
import Foundation

signal(SIGPIPE, SIG_IGN)   // ffmpeg morreu? tratamos no write, não crashamos

let SR = 48000.0
func elog(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

// ---- mixagem: sistema é o relógio-mestre; mic entra de uma fila pendente ----
final class Mixer: NSObject, SCStreamOutput {
    let out = FileHandle.standardOutput
    var micPending = [Float]()            // amostras de mic aguardando mixagem
    let maxPending = Int(SR * 2)          // teto 2s (evita crescer se o sistema travar)
    var sysFrames = 0, micFrames = 0
    var broken = false

    // downmix → mono, ciente do formato: sistema vem Float32 não-interleaved (stereo);
    // mic vem Int16 interleaved (mono). Converte ambos p/ Float [-1,1].
    private func mono(_ sb: CMSampleBuffer) -> [Float]? {
        guard let fd = CMSampleBufferGetFormatDescription(sb),
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fd)?.pointee else { return nil }
        let isFloat = (asbd.mFormatFlags & kAudioFormatFlagIsFloat) != 0
        let nonInter = (asbd.mFormatFlags & kAudioFormatFlagIsNonInterleaved) != 0
        let ch = max(1, Int(asbd.mChannelsPerFrame))
        let frames = Int(CMSampleBufferGetNumSamples(sb))
        guard frames > 0 else { return [] }

        var block: CMBlockBuffer?
        let maxB = nonInter ? ch : 1
        let abl = AudioBufferList.allocate(maximumBuffers: maxB)
        defer { free(abl.unsafeMutablePointer) }
        let st = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sb, bufferListSizeNeededOut: nil, bufferListOut: abl.unsafeMutablePointer,
            bufferListSize: AudioBufferList.sizeInBytes(maximumBuffers: maxB),
            blockBufferAllocator: nil, blockBufferMemoryAllocator: nil,
            flags: kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,
            blockBufferOut: &block)
        guard st == noErr, abl.count > 0 else { return nil }

        var out = [Float](repeating: 0, count: frames)
        let invI16 = Float(1.0 / 32768.0)
        if nonInter {                                   // 1 canal por buffer
            for b in abl {
                guard let p = b.mData else { continue }
                if isFloat { let f = p.bindMemory(to: Float.self, capacity: frames)
                    for i in 0..<frames { out[i] += f[i] } }
                else { let s = p.bindMemory(to: Int16.self, capacity: frames)
                    for i in 0..<frames { out[i] += Float(s[i]) * invI16 } }
            }
            if abl.count > 1 { let inv = 1.0 / Float(abl.count); for i in 0..<frames { out[i] *= inv } }
        } else {                                        // interleaved: 1 buffer, canais em stride
            guard let p = abl[0].mData else { return [] }
            if isFloat { let f = p.bindMemory(to: Float.self, capacity: frames * ch)
                for i in 0..<frames { var a: Float = 0; for c in 0..<ch { a += f[i*ch+c] }; out[i] = a / Float(ch) } }
            else { let s = p.bindMemory(to: Int16.self, capacity: frames * ch)
                for i in 0..<frames { var a: Float = 0; for c in 0..<ch { a += Float(s[i*ch+c]) * invI16 }; out[i] = a / Float(ch) } }
        }
        return out
    }

    private func writeMono(_ samples: [Float]) {
        if broken { return }
        samples.withUnsafeBytes { raw in
            do { try out.write(contentsOf: Data(raw)) }
            catch { broken = true; elog("stdout fechada (ffmpeg saiu) — encerrando"); cleanupAndExit(0) }
        }
    }

    var loggedSys = false, loggedMic = false
    private func logFormatOnce(_ sb: CMSampleBuffer, _ tag: String) {
        guard let fd = CMSampleBufferGetFormatDescription(sb),
              let a = CMAudioFormatDescriptionGetStreamBasicDescription(fd)?.pointee else { return }
        // fmtFlags bit0=Float bit1=BigEndian bit3=Packed bit5=NonInterleaved
        elog("\(tag) fmt: sr=\(a.mSampleRate) ch=\(a.mChannelsPerFrame) bits=\(a.mBitsPerChannel) flags=\(a.mFormatFlags)")
    }

    func stream(_ s: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        guard CMSampleBufferDataIsReady(sb) else { return }
        if type == .microphone, !loggedMic { loggedMic = true; logFormatOnce(sb, "MIC") }
        if type == .audio, !loggedSys { loggedSys = true; logFormatOnce(sb, "SYS") }
        guard let m = mono(sb), !m.isEmpty else { return }
        if type == .microphone {
            micFrames += 1
            micPending.append(contentsOf: m)
            if micPending.count > maxPending {                 // descarta o excesso antigo
                micPending.removeFirst(micPending.count - maxPending)
            }
            return
        }
        // type == .audio (sistema) → mistura com o mic pendente e emite
        sysFrames += 1
        var mixed = m
        let take = min(m.count, micPending.count)
        for i in 0..<take { mixed[i] += micPending[i] }
        if take > 0 { micPending.removeFirst(take) }
        writeMono(mixed)
    }
}

let mixer = Mixer()
var theStream: SCStream?

func cleanupAndExit(_ code: Int32) {
    if let st = theStream { st.stopCapture { _ in } }
    try? mixer.out.close()
    elog("fim — sys=\(mixer.sysFrames) mic=\(mixer.micFrames) buffers")
    exit(code)
}

// SIGTERM/SIGINT (Hammerspoon manda SIGTERM ao parar) → finaliza limpo.
// IMPORTANTE: reter as sources (senão são desalocadas e o sinal volta a ser ignorado).
var signalSources = [DispatchSourceSignal]()
for sig in [SIGTERM, SIGINT] {
    signal(sig, SIG_IGN)
    let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    src.setEventHandler { cleanupAndExit(0) }
    src.resume()
    signalSources.append(src)
}

Task {
    do {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else { elog("sem display"); exit(2) }
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.capturesAudio = true
        cfg.sampleRate = Int(SR)
        cfg.channelCount = 2
        cfg.excludesCurrentProcessAudio = true
        cfg.captureMicrophone = true          // macOS 15+: mic no mesmo stream/relógio
        cfg.width = 2; cfg.height = 2
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        let stream = SCStream(filter: filter, configuration: cfg, delegate: nil)
        let q = DispatchQueue(label: "voxlog.audio")   // uma fila serial p/ os 2 outputs → sem locks
        try stream.addStreamOutput(mixer, type: .audio, sampleHandlerQueue: q)
        try stream.addStreamOutput(mixer, type: .microphone, sampleHandlerQueue: q)
        try await stream.startCapture()
        theStream = stream
        elog("gravando (nativo SCK: sistema+mic → mono)")
    } catch {
        elog("ERRO SCK: \(error)")
        exit(1)
    }
}
dispatchMain()
