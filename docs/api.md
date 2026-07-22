# TalkToMe POST API

Base path: `/api/v1`. Exactly nine operations are exposed, all with `POST`. JSON field names are
camelCase. Every response uses one envelope:

```json
{
  "version": 1,
  "reasonCode": 200,
  "reasonText": "OK"
}
```

The HTTP status equals `reasonCode`. Unknown fields and legacy names are validation errors.

## 1. `POST /api/v1/textToSpeech`

```json
{
  "values": ["First message", "Second message"],
  "importance": "high",
  "volumeMultiplier": 0.8,
  "calculateStats": true,
  "waitUntilPlaybackFinished": true
}
```

Exactly one of `value` and `values` is required. `values` retains the existing pre-segmented array
form and may be `null` or empty for a successful no-op. It accepts at most 255 items and 16,384
Unicode code points per item, including the full 255×16,384 combination. A string in `values` is
invalid.

The singular form accepts one string:

```json
{
  "value": "First sentence. Second sentence? Wait {{pause(500)}} and continue.",
  "importance": "high"
}
```

Before queueing, `value` is converted into the canonical `values` array. Ordinary text is split
at the same language-aware sentence boundaries that the selected Piper voice obtains from its
phonemizer. For eSpeak voices this uses eSpeak NG clause classification rather than a plain
`.?!` character split, so punctuation in contexts such as `3.14` is not treated as a sentence
boundary. Original text, punctuation, and surrounding whitespace are preserved. Supported play
and pause tokens are isolated as their own values before sentence segmentation. The transformed
request is then archived and processed exactly like an explicit `values` request. More than 255
resulting values or any resulting value over 16,384 Unicode code points returns 413.

`importance` is `high` or `low` and defaults to `high`. A `high` request is appended to the
queue whenever capacity is available. A `low` request is accepted only when the queue has no
active job. If the queue is busy, it returns 200 without creating a job. The other flags default
to false.

`volumeMultiplier` is an optional floating-point number and defaults to `1`. Values below `0`
are clamped to `0` and values above `1` are clamped to `1`. The multiplier is applied to the
chosen setup volume and the result is rounded to the nearest integer for that job.

A standalone value such as `{{play('positive_gong.wav')}}` plays the named WAV from
`master-data/sounds` instead of sending the value to a synthesis worker. The `play` syntax is
case-sensitive and ignores whitespace surrounding the whole command. Paths may address nested
folders, but they must remain inside `master-data/sounds`. A missing file, an attempt to escape
that directory, or a WAV that is not mono at 22,050 Hz fails that value and is reported in job
errors to a waiting or statistics request. For an explicit `values` array, a command embedded in
a longer value remains ordinary text. In singular `value` input, supported commands are isolated
before sentence segmentation.

A standalone `{{pause(1000)}}` value plays the required integer number of milliseconds of
silence. Pause commands are case-sensitive and ignore surrounding whitespace. Integer durations
below zero are clamped to 0 ms and durations above
15,000 are clamped to 15,000 ms. A pause parameter that is not an integer is skipped without
synthesis or audio playback. A pause token embedded in an explicit `values` item remains ordinary
text, while singular `value` input isolates it during transformation.

An immediate non-waiting response contains `jobId`:

```json
{
  "version": 1,
  "reasonCode": 200,
  "reasonText": "Accepted",
  "jobId": "2026_07_18_14_30_00_0000"
}
```

A waiting/statistics response contains the terminal `job`. `stats` is added when requested. When
`calculateStats` is `true`, every entry in `job.values` also contains the zero-based
`workerIndex` of the process that synthesized that value and `totalWorkers` from the job settings
snapshot:

```json
{
  "job": {
    "values": [
      {
        "id": "2026_07_18_14_30_00_0000-0",
        "index": 0,
        "workerIndex": 2,
        "totalWorkers": 4,
        "text": "First message",
        "state": "finished"
      }
    ]
  }
}
```

`workerIndex` is in the range `0` through `totalWorkers - 1`. Play and pause values do not use a
worker, so their `workerIndex` is `null`. A value that failed before a worker returned a synthesis
result also has `null` as its `workerIndex`. The terminal object is removed from the in-memory
queue after the response is handed to the client.

## 2. `POST /api/v1/queueInfo`

The optional request body selects the response detail level:

```json
{"mode": "min"}
```

`mode` is `min` or `max`. A missing body, `{}`, or a missing `mode` defaults to `max`. The `min`
response is intended for inexpensive polling and contains no job text:

```json
{
  "version": 1,
  "reasonCode": 200,
  "reasonText": "OK",
  "hasActiveJobs": true,
  "activeJobCount": 2
}
```

The count includes only nonterminal jobs in `waiting`, `processing`, `processed`, or `playing`
state. A terminal job retained briefly for a waiting client is excluded. `hasActiveJobs` is true
exactly when `activeJobCount` is greater than zero.

The `max` response adds `jobs` in queue order. Each active job contains its state, timestamps,
settings snapshot, errors, and all parsed values. Values include their text, state, timestamps,
`workerIndex`, and `totalWorkers`. An empty queue returns `jobs: []`.

## 3. `POST /api/v1/stop`

Request may have no body or `{}`. The operation atomically cancels all active jobs and their
unfinished values, stops active audio playback, and leaves the synthesis worker pool available
for later requests. Synthesis already executing in a worker may finish in the background, but its
cancelled result is not played. A successful response reports the number of cancelled jobs:

```json
{
  "version": 1,
  "reasonCode": 200,
  "reasonText": "Playback stopped",
  "cancelledJobs": 2
}
```

## 4. `POST /api/v1/getSetup`

Request may have no body or `{}`. Response payload:

```json
{
  "version": 1,
  "reasonCode": 200,
  "reasonText": "OK",
  "setup": {
    "version": 1,
    "network": {
      "ipv4Address": "127.0.0.1",
      "ipv4Enabled": true,
      "ipv6Address": "::1",
      "ipv6Enabled": true,
      "port": 44448,
      "remoteManagementEnabled": true
    },
    "voice": {
      "tts": "Piper",
      "speaker": "en_US-ljspeech-medium",
      "volume": 100
    },
    "general": {
      "device": "CPU",
      "workers": 4,
      "directories": {
        "tempDirectory": "./data/temp",
        "speechDirectory": "./data/speech",
        "textDirectory": "./data/text",
        "garbageCollectorTimeout": 1000000000
      },
      "theme": "light"
    },
    "limits": {
      "maxQueuedJobs": 100,
      "maxRequestBodyBytes": 67108864
    }
  }
}
```

## 5. `POST /api/v1/setSetup`

Send the complete setup returned by `getSetup`, never a partial patch:

```json
{
  "setup": {
    "version": 1,
    "network": {
      "ipv4Address": "127.0.0.1",
      "ipv4Enabled": true,
      "ipv6Address": "::1",
      "ipv6Enabled": true,
      "port": 44448,
      "remoteManagementEnabled": true
    },
    "voice": {
      "tts": "Piper",
      "speaker": "en_US-ljspeech-medium",
      "volume": 72
    },
    "general": {
      "device": "CPU",
      "workers": 4,
      "directories": {"tempDirectory": "./data/temp", "speechDirectory": "./data/speech", "textDirectory": "./data/text", "garbageCollectorTimeout": 1000000000},
      "theme": "dark"
    },
    "limits": {"maxQueuedJobs": 100, "maxRequestBodyBytes": 67108864}
  }
}
```

The response repeats the saved setup and adds, for example:

```json
{"restartRequired": true, "restartFields": ["network.port"]}
```

Live fields apply without restarting; restart fields are only reported. The server never
restarts itself.

## 6. `POST /api/v1/getVoices`

Request: `{}`. Response `voices` is an array whose entries include `id`, `name`, `language`,
`quality`, `sizeBytes`, `license`, `source`, `status`, `downloadable`, and `blockedReason`.
`status` is `ready`, `downloadRequired`, `downloading`, or `invalid`. Each descriptor also
includes `requiresLicenseConfirmation` and `licenseNotice`. An uninstalled official voice with
download metadata remains `downloadRequired`; `requiresLicenseConfirmation` tells clients that
its denied, unknown, or missing license needs explicit acknowledgement. `licenseNotice` is the
nullable warning to show before that acknowledgement. `blockedReason` is retained only when a
record is genuinely invalid or unavailable.

## 7. `POST /api/v1/downloadVoice`

```json
{"voiceId": "en_US-amy-medium", "licenseConfirmed": false}
```

`licenseConfirmed` defaults to `false`. A freely licensed catalog voice downloads normally. A
voice with a denied, unknown, or missing license returns 403 unless this field is `true`.
Confirmation applies to that download attempt only; it does not bypass transport, hash,
validation, or conflict checks. A successful response contains the installed `voice`
descriptor. Downloads are staged, size-bounded, hash-checked when catalog hashes exist, and
validated before installation. In the portal, a downloaded voice is only selected in the setup
draft; it becomes the active voice after an explicit Voice Setup Save.

## 8. `POST /api/v1/deleteVoice`

```json
{"voiceId": "en_US-amy-medium"}
```

Deletes the installed files for an official or custom voice. An official voice remains in the
catalog with `downloadRequired` status and can be downloaded again. A custom voice disappears
from the catalog. Deleting a voice that is not installed returns 404.

## 9. `POST /api/v1/importVoice`

This endpoint accepts only a local `multipart/form-data` upload, with `model`, `config`,
`displayName`, `license`, and `rightsConfirmed=true` fields. The files must be one Piper `.onnx`
model and its `.onnx.json` config. JSON requests, including URL-based import requests, receive
HTTP 415 with `Only multipart local voice import is supported`.

## Status and reason codes

| Code | Meaning |
| --- | --- |
| 200 | accepted, completed, saved, or successful no-op |
| 400 | invalid JSON/schema, malformed multipart, missing rights confirmation |
| 403 | remote management denied or restricted voice license |
| 404 | operation resource/voice not found |
| 405 | non-POST API method |
| 409 | voice already exists or activation conflict |
| 413 | request body, item count, or item length exceeds a limit |
| 415 | import request is not a multipart local voice upload |
| 429 | 100 active jobs already admitted |
| 500 | sanitized unexpected/synthesis failure; correlation ID is returned |
| 502 | voice download/import transport, validation, or checksum failure |
| 503 | runtime, worker pool, voice service, or audio device unavailable |
| 507 | request archive is not writable |

Management operations (`getSetup`, `setSetup`, `getVoices`, `downloadVoice`, `deleteVoice`,
`importVoice`) are loopback-only unless remote management was enabled and the process
deliberately restarted.
`textToSpeech`, `queueInfo`, and `stop` remain callable from a configured LAN listener.
