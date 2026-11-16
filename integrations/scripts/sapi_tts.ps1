# Lokale Windows-Sprachsynthese (System.Speech) mit Wort-Zeitstempeln.
# Aufruf: powershell -NoProfile -ExecutionPolicy Bypass -File sapi_tts.ps1 -JobFile job.json
# job.json: {"voice": "...", "rate": 0, "items": [{"text_file": "...", "wav": "...", "timings": "..."}]}
param([Parameter(Mandatory = $true)][string]$JobFile)
$ErrorActionPreference = "Stop"
Add-Type -ReferencedAssemblies System.Speech -TypeDefinition @"
using System;
using System.Globalization;
using System.Speech.Synthesis;
using System.Speech.AudioFormat;
using System.Text;
public static class BobTts {
    public static string Speak(string text, string wav, string voice, int rate) {
        var sb = new StringBuilder("[");
        bool first = true;
        using (var s = new SpeechSynthesizer()) {
            if (!String.IsNullOrEmpty(voice)) { s.SelectVoice(voice); }
            s.Rate = rate;
            s.SetOutputToWaveFile(wav, new SpeechAudioFormatInfo(44100, AudioBitsPerSample.Sixteen, AudioChannel.Mono));
            s.SpeakProgress += (o, e) => {
                if (!first) { sb.Append(","); }
                first = false;
                sb.Append("{\"t\":");
                sb.Append(e.AudioPosition.TotalMilliseconds.ToString(CultureInfo.InvariantCulture));
                sb.Append(",\"pos\":"); sb.Append(e.CharacterPosition);
                sb.Append(",\"len\":"); sb.Append(e.CharacterCount);
                sb.Append("}");
            };
            s.Speak(text);
            s.SetOutputToNull();
        }
        sb.Append("]");
        return sb.ToString();
    }
}
"@
$job = Get-Content -Raw -Encoding UTF8 $JobFile | ConvertFrom-Json
$utf8 = New-Object System.Text.UTF8Encoding($false)
foreach ($item in $job.items) {
    $text = [System.IO.File]::ReadAllText($item.text_file, $utf8)
    $json = [BobTts]::Speak($text, $item.wav, $job.voice, [int]$job.rate)
    [System.IO.File]::WriteAllText($item.timings, $json, $utf8)
}
