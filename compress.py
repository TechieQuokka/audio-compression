#!/usr/bin/env python3
"""
Dynamic Range Compression CLI
오디오 파일에 다이나믹 레인지 압축 및 LUFS 정규화 적용
"""

import argparse
import json
import os
import re
import sys
import soundfile as sf
import numpy as np
from compressor import DynamicRangeCompressor
from lufs_meter import LUFSMeter


def load_config(config_path):
    """
    JSON 설정 파일 로드 (전체)

    Args:
        config_path: JSON 파일 경로

    Returns:
        dict: 전체 설정 딕셔너리
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"❌ Error: Config file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {config_path}: {e}")
        sys.exit(1)


def extract_metadata(config):
    """
    JSON에서 메타데이터 추출

    Args:
        config: 전체 설정 딕셔너리

    Returns:
        dict: 메타데이터 (dynamic_range, bandwidth, gate_threshold)
    """
    metadata = {
        'dynamic_range': None,
        'bandwidth': None,
        'gate_threshold': None
    }

    # Dynamic range 추출 (compression.reason에서)
    if 'compression' in config and 'reason' in config['compression']:
        reason = config['compression']['reason']
        # "Large dynamic range (30.6 dB)" 형식에서 숫자 추출
        match = re.search(r'(\d+\.?\d*)\s*dB', reason)
        if match:
            metadata['dynamic_range'] = float(match.group(1))

    # Bandwidth 추출 (voice_enhancement.reason에서)
    if 'voice_enhancement' in config and 'reason' in config['voice_enhancement']:
        reason = config['voice_enhancement']['reason']
        # "Wide bandwidth (9755 Hz)" 형식에서 숫자 추출
        match = re.search(r'(\d+)\s*Hz', reason)
        if match:
            metadata['bandwidth'] = int(match.group(1))

    # Gate threshold 추출 (noise_reduction에서)
    if 'noise_reduction' in config and 'gate_threshold' in config['noise_reduction']:
        metadata['gate_threshold'] = config['noise_reduction']['gate_threshold']

    return metadata


def calculate_adaptive_params(metadata, base_params):
    """
    메타데이터 기반 adaptive parameter 계산

    Args:
        metadata: 추출된 메타데이터
        base_params: 기본 파라미터 (JSON compression 섹션 또는 기본값)

    Returns:
        dict: 최적화된 파라미터
    """
    params = base_params.copy()

    # Dynamic range 기반 ratio 조정
    if metadata['dynamic_range'] is not None:
        dr = metadata['dynamic_range']
        if dr > 25:
            # 큰 다이나믹 레인지: 더 강한 압축
            params['ratio'] = params.get('ratio', 4.0)
        elif dr > 15:
            # 중간: 적당한 압축
            params['ratio'] = params.get('ratio', 3.0)
        else:
            # 작은 다이나믹 레인지: 약한 압축
            params['ratio'] = params.get('ratio', 2.0)

    # Gate threshold 기반 compressor threshold 조정
    if metadata['gate_threshold'] is not None:
        # Gate threshold보다 10dB 높게 설정
        suggested_threshold = metadata['gate_threshold'] + 10
        if 'threshold' not in params:
            params['threshold'] = suggested_threshold

    # Bandwidth 기반 attack/release 조정
    if metadata['bandwidth'] is not None:
        bw = metadata['bandwidth']
        if bw > 8000:
            # 광대역: 빠른 attack/release (디테일 보존)
            params['attack'] = params.get('attack', 3.0)
            params['release'] = params.get('release', 40.0)
        else:
            # 협대역: 느린 attack/release (부드럽게)
            params['attack'] = params.get('attack', 7.0)
            params['release'] = params.get('release', 60.0)

    return params


def parse_args():
    """CLI 인자 파싱"""
    parser = argparse.ArgumentParser(
        description='Dynamic Range Compression with LUFS normalization\n\n'
                    'Adaptive compression based on audio metadata (dynamic range, bandwidth, gate threshold)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # JSON 설정 사용 (adaptive parameters)
  python compress.py --input input.wav --output output.wav --config config.json

  # 수동 파라미터 지정
  python compress.py --input input.wav --output output.wav --ratio 4.0 --threshold -18

  # LUFS만 정규화 (압축 없음)
  python compress.py --input input.wav --output output.wav --ratio 1.0 --target-lufs -16

Adaptive Parameters:
  When using --config, the following metadata is automatically extracted and used:

  - dynamic_range (from compression.reason): Auto-adjusts compression ratio
    • > 25 dB: Strong compression (ratio 4:1)
    • 15-25 dB: Medium compression (ratio 3:1)
    • < 15 dB: Light compression (ratio 2:1)

  - gate_threshold (from noise_reduction): Auto-adjusts compressor threshold
    • Threshold = gate_threshold + 10 dB

  - bandwidth (from voice_enhancement.reason): Auto-adjusts attack/release
    • > 8000 Hz: Fast attack/release (preserve detail)
    • < 8000 Hz: Slow attack/release (smooth)

Parameter Priority:
  CLI options > JSON compression section > Adaptive calculation > Default values
        """
    )

    # 필수 인자
    parser.add_argument('--input', '-i', required=True,
                        help='입력 WAV 파일 경로 (필수)')
    parser.add_argument('--output', '-o', required=True,
                        help='출력 WAV 파일 경로 (필수)')

    # 선택 인자
    parser.add_argument('--config', '-c',
                        help='JSON 설정 파일 경로 (선택)')

    # Compressor 파라미터
    parser.add_argument('--ratio', type=float, default=None,
                        help='압축 비율 (예: 3.0 = 3:1), 기본값: 3.0 또는 JSON 설정')
    parser.add_argument('--threshold', type=float, default=None,
                        help='압축 시작 레벨 (dB), 기본값: -20 또는 JSON 설정')
    parser.add_argument('--attack', type=float, default=None,
                        help='압축 시작 시간 (ms), 기본값: 5 또는 JSON 설정')
    parser.add_argument('--release', type=float, default=None,
                        help='압축 해제 시간 (ms), 기본값: 50 또는 JSON 설정')
    parser.add_argument('--knee', type=float, default=3.0,
                        help='Soft knee 크기 (dB), 기본값: 3.0')

    # LUFS 파라미터
    parser.add_argument('--target-lufs', type=float, default=-16.0,
                        help='목표 LUFS 레벨, 기본값: -16.0 (방송 표준)')

    # 기타
    parser.add_argument('--no-normalize', action='store_true',
                        help='LUFS 정규화 비활성화 (압축만 적용)')

    return parser.parse_args()


def main():
    """메인 실행 함수"""
    args = parse_args()

    # 입력 파일 확인
    if not os.path.exists(args.input):
        print(f"❌ Error: Input file not found: {args.input}")
        sys.exit(1)

    # 출력 디렉토리 생성
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"📁 Created output directory: {output_dir}")

    # 설정 로드 및 adaptive parameter 계산
    full_config = {}
    compression_config = {}
    metadata = {}

    if args.config:
        print(f"📄 Loading config from: {args.config}")
        full_config = load_config(args.config)

        # Compression 섹션 추출
        compression_config = full_config.get('compression', {})

        # 메타데이터 추출
        metadata = extract_metadata(full_config)
        print(f"\n🔍 Extracted Metadata:")
        if metadata['dynamic_range']:
            print(f"   Dynamic Range: {metadata['dynamic_range']} dB")
        if metadata['bandwidth']:
            print(f"   Bandwidth: {metadata['bandwidth']} Hz")
        if metadata['gate_threshold']:
            print(f"   Gate Threshold: {metadata['gate_threshold']} dB")

        # Adaptive parameter 계산
        adaptive_params = calculate_adaptive_params(metadata, compression_config)
        print(f"\n⚡ Adaptive Parameters:")
        print(f"   Calculated from metadata: {adaptive_params}")
    else:
        adaptive_params = {}

    # 파라미터 우선순위: CLI > JSON compression > Adaptive > 기본값
    ratio = args.ratio if args.ratio is not None else compression_config.get('ratio', adaptive_params.get('ratio', 3.0))
    threshold = args.threshold if args.threshold is not None else compression_config.get('threshold', adaptive_params.get('threshold', -20.0))
    attack = args.attack if args.attack is not None else compression_config.get('attack', adaptive_params.get('attack', 5.0))
    release = args.release if args.release is not None else compression_config.get('release', adaptive_params.get('release', 50.0))
    knee = args.knee

    print("\n" + "="*60)
    print("🎛️  DYNAMIC RANGE COMPRESSION")
    print("="*60)

    # 오디오 로드
    print(f"\n📥 Loading: {args.input}")
    audio, sample_rate = sf.read(args.input)
    print(f"   Sample rate: {sample_rate} Hz")
    print(f"   Shape: {audio.shape}")
    print(f"   Duration: {len(audio) / sample_rate:.2f} seconds")

    # Compressor 초기화
    compressor = DynamicRangeCompressor(
        threshold=threshold,
        ratio=ratio,
        attack=attack,
        release=release,
        knee=knee,
        sample_rate=sample_rate
    )

    print(f"\n⚙️  Compressor Settings:")
    print(f"   Threshold: {threshold} dB")
    print(f"   Ratio: {ratio}:1")
    print(f"   Attack: {attack} ms")
    print(f"   Release: {release} ms")
    print(f"   Knee: {knee} dB")

    # 압축 전 통계
    lufs_meter = LUFSMeter(sample_rate=sample_rate, target_lufs=args.target_lufs)
    print(f"\n📊 Original Audio Statistics:")
    original_stats = lufs_meter.get_loudness_stats(audio)
    print(f"   Integrated LUFS: {original_stats['integrated_lufs']:.2f} LUFS")
    print(f"   Peak: {original_stats['peak_db']:.2f} dB")
    print(f"   RMS: {original_stats['rms_db']:.2f} dB")
    print(f"   Crest Factor: {original_stats['crest_factor_db']:.2f} dB")

    # LRA (Loudness Range) 측정
    original_lra = lufs_meter.analyze_dynamic_range(audio)
    print(f"   Loudness Range (LRA): {original_lra:.2f} LU")

    # 압축 적용
    print(f"\n🔧 Applying compression...")
    compressed = compressor.compress(audio)

    # 압축 통계
    comp_stats = compressor.get_stats(audio, compressed)
    print(f"\n📈 Compression Results:")
    print(f"   Original Dynamic Range: {comp_stats['original_dynamic_range_db']:.2f} dB")
    print(f"   Compressed Dynamic Range: {comp_stats['compressed_dynamic_range_db']:.2f} dB")
    print(f"   Reduction: {comp_stats['original_dynamic_range_db'] - comp_stats['compressed_dynamic_range_db']:.2f} dB")

    # LUFS 정규화
    if not args.no_normalize:
        print(f"\n🎚️  LUFS Normalization:")
        print(f"   Target LUFS: {args.target_lufs} LUFS")

        # 압축 후 LUFS 측정
        compressed_lufs = lufs_meter.measure_lufs(compressed)
        print(f"   Current LUFS: {compressed_lufs:.2f} LUFS")

        # 정규화
        normalized, makeup_gain = lufs_meter.normalize_to_target(compressed, compressed_lufs)
        print(f"   Makeup Gain: {makeup_gain:+.2f} dB")

        final_audio = normalized
    else:
        print(f"\n⏭️  Skipping LUFS normalization (--no-normalize)")
        final_audio = compressed

    # 최종 통계
    print(f"\n✅ Final Audio Statistics:")
    final_stats = lufs_meter.get_loudness_stats(final_audio)
    print(f"   Integrated LUFS: {final_stats['integrated_lufs']:.2f} LUFS")
    print(f"   Peak: {final_stats['peak_db']:.2f} dB")
    print(f"   RMS: {final_stats['rms_db']:.2f} dB")

    final_lra = lufs_meter.analyze_dynamic_range(final_audio)
    print(f"   Loudness Range (LRA): {final_lra:.2f} LU")

    # 저장
    print(f"\n💾 Saving: {args.output}")
    sf.write(args.output, final_audio, sample_rate)
    print(f"   ✅ Done!")

    print("\n" + "="*60)
    print("🎉 Processing Complete!")
    print("="*60)
    print(f"\nSummary:")
    print(f"  Input:  {args.input}")
    print(f"  Output: {args.output}")
    print(f"  LUFS:   {original_stats['integrated_lufs']:.2f} → {final_stats['integrated_lufs']:.2f} LUFS")
    print(f"  LRA:    {original_lra:.2f} → {final_lra:.2f} LU")
    print()


if __name__ == '__main__':
    main()
