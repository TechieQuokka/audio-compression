# Dynamic Range Compression

오디오의 다이나믹 레인지를 압축하고 LUFS(Loudness Units relative to Full Scale)로 정규화하는 도구

## 🎯 목적

볼륨 편차를 줄여 **일관된 청취 경험** 제공

- 속삭임과 외침의 볼륨 차이 축소
- 방송 표준(-16 LUFS) 준수
- 자연스러운 압축 (Soft Knee, Attack/Release)

## 📦 설치

```bash
cd /home/beethoven/workspace/deeplearning/project/autokr2/compression
pip install -r requirements.txt
```

## 🚀 사용법

### 기본 사용 (JSON 설정 파일 활용)

```bash
python compress.py \
  --input /path/to/input.wav \
  --output /path/to/output.wav \
  --config /path/to/config.json
```

**JSON 형식** (`config.json`):
```json
{
  "compression": {
    "ratio": 3.0,
    "threshold": -20,
    "attack": 5,
    "release": 50,
    "reason": "Large dynamic range (30.6 dB)"
  }
}
```

### 수동 파라미터 지정

```bash
python compress.py \
  --input input.wav \
  --output output.wav \
  --ratio 4.0 \
  --threshold -18 \
  --attack 10 \
  --release 100 \
  --target-lufs -16
```

### 프로젝트 예제

```bash
# 입력 파일
INPUT="/home/beethoven/workspace/deeplearning/project/autokr2/data/enhancement_audio_data/[SubsPlease] Yasei no Last Boss ga Arawareta! - 08 (480p) [30425761].wav"

# 출력 파일 (원본 파일명 유지)
OUTPUT="/home/beethoven/workspace/deeplearning/project/autokr2/data/compression_audio_data/[SubsPlease] Yasei no Last Boss ga Arawareta! - 08 (480p) [30425761].wav"

# 설정 파일
CONFIG="/home/beethoven/workspace/deeplearning/project/autokr2/data/audio_data/[SubsPlease] Yasei no Last Boss ga Arawareta! - 08 (480p) [30425761].json"

# 실행
python compress.py --input "$INPUT" --output "$OUTPUT" --config "$CONFIG"
```

## ⚙️ 파라미터 설명

### Compressor 파라미터

| 파라미터 | 설명 | 기본값 | 범위 |
|---------|------|--------|------|
| `--ratio` | 압축 비율 (N:1) | 3.0 | 1.0 ~ 20.0 |
| `--threshold` | 압축 시작 레벨 (dB) | -20 | -60 ~ 0 |
| `--attack` | 압축 시작 시간 (ms) | 5 | 0.1 ~ 100 |
| `--release` | 압축 해제 시간 (ms) | 50 | 10 ~ 1000 |
| `--knee` | Soft knee 크기 (dB) | 3 | 0 ~ 10 |

### LUFS 파라미터

| 파라미터 | 설명 | 기본값 |
|---------|------|--------|
| `--target-lufs` | 목표 라우드니스 | -16.0 LUFS |
| `--no-normalize` | LUFS 정규화 비활성화 | False |

### 파라미터 우선순위

1. **CLI 옵션** (최우선)
2. **JSON 설정 파일** (--config 지정 시)
3. **기본값**

## 📊 출력 예시

```
============================================================
🎛️  DYNAMIC RANGE COMPRESSION
============================================================

📥 Loading: input.wav
   Sample rate: 44100 Hz
   Shape: (2205000, 2)
   Duration: 50.00 seconds

⚙️  Compressor Settings:
   Threshold: -20.0 dB
   Ratio: 3.0:1
   Attack: 5.0 ms
   Release: 50.0 ms
   Knee: 3.0 dB

📊 Original Audio Statistics:
   Integrated LUFS: -22.35 LUFS
   Peak: -3.14 dB
   RMS: -25.42 dB
   Crest Factor: 22.28 dB
   Loudness Range (LRA): 12.45 LU

🔧 Applying compression...

📈 Compression Results:
   Original Dynamic Range: 30.60 dB
   Compressed Dynamic Range: 16.23 dB
   Reduction: 14.37 dB

🎚️  LUFS Normalization:
   Target LUFS: -16.0 LUFS
   Current LUFS: -19.28 LUFS
   Makeup Gain: +3.28 dB

✅ Final Audio Statistics:
   Integrated LUFS: -16.00 LUFS
   Peak: -1.42 dB
   RMS: -19.15 dB
   Loudness Range (LRA): 8.31 LU

💾 Saving: output.wav
   ✅ Done!

============================================================
🎉 Processing Complete!
============================================================

Summary:
  Input:  input.wav
  Output: output.wav
  LUFS:   -22.35 → -16.00 LUFS
  LRA:    12.45 → 8.31 LU
```

## 🔧 알고리즘 상세

### 1. Compressor

- **Envelope Detection**: RMS 기반 레벨 측정
- **Gain Reduction**: Threshold, Ratio, Knee 기반 계산
- **Soft Knee**: 부드러운 압축 시작점
- **Attack/Release**: Exponential smoothing으로 자연스러운 변화

### 2. LUFS Meter

- **ITU-R BS.1770-4**: 국제 방송 표준
- **K-weighting**: 인간 청각 특성 반영
- **Integrated LUFS**: 전체 라우드니스 측정
- **Makeup Gain**: 목표 LUFS 달성을 위한 자동 조정

### 3. 처리 플로우

```
입력 오디오
    ↓
RMS Envelope Detection
    ↓
Gain Reduction 계산
    ↓
Attack/Release 적용
    ↓
압축된 오디오
    ↓
LUFS 측정
    ↓
Makeup Gain 적용
    ↓
출력 오디오 (-16 LUFS)
```

## ⚠️ 주의사항

### 과도한 압축 방지

- **Ratio**: 4:1 이하 권장
- **Attack**: 너무 빠르면 "펌핑" 현상
- **Release**: 너무 느리면 부자연스러움
- **Knee**: Soft knee 사용 (Hard knee는 거친 소리)

### Peak Limiting

- 출력이 0dBFS를 초과하면 자동으로 peak limiting 적용
- Makeup gain이 줄어들 수 있음

## 📚 참고 자료

- [ITU-R BS.1770-4](https://www.itu.int/rec/R-REC-BS.1770/en): LUFS 표준
- [Dynamic Range Compression](https://en.wikipedia.org/wiki/Dynamic_range_compression): 압축 기초
- [pyloudnorm](https://github.com/csteinmetz1/pyloudnorm): LUFS 측정 라이브러리

## 📄 라이선스

MIT License
