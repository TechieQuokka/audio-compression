#!/usr/bin/env python3
"""
Dynamic Range Compression CLI
오디오 파일에 다이나믹 레인지 압축 및 LUFS 정규화 적용
"""

import argparse
import json
import os
import sys
import soundfile as sf
import numpy as np
from compressor import DynamicRangeCompressor
from lufs_meter import LUFSMeter


def load_config(config_path):
    """
    JSON 설정 파일 로드

    Args:
        config_path: JSON 파일 경로

    Returns:
        dict: 설정 딕셔너리 (compression 섹션)
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # compression 섹션 추출
        if 'compression' in config:
            return config['compression']
        else:
            print(f"⚠️  Warning: 'compression' section not found in {config_path}")
            return {}
    except FileNotFoundError:
        print(f"❌ Error: Config file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {config_path}: {e}")
        sys.exit(1)


def parse_args():
    """CLI 인자 파싱"""
    parser = argparse.ArgumentParser(
        description='Dynamic Range Compression with LUFS normalization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # JSON 설정 사용
  python cli.py --input input.wav --output output.wav --config config.json

  # 수동 파라미터 지정
  python cli.py --input input.wav --output output.wav --ratio 4.0 --threshold -18

  # LUFS만 정규화 (압축 없음)
  python cli.py --input input.wav --output output.wav --ratio 1.0 --target-lufs -16
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

    # 설정 로드
    config = {}
    if args.config:
        print(f"📄 Loading config from: {args.config}")
        config = load_config(args.config)
        print(f"   Config loaded: {config}")

    # 파라미터 우선순위: CLI > JSON > 기본값
    ratio = args.ratio if args.ratio is not None else config.get('ratio', 3.0)
    threshold = args.threshold if args.threshold is not None else config.get('threshold', -20.0)
    attack = args.attack if args.attack is not None else config.get('attack', 5.0)
    release = args.release if args.release is not None else config.get('release', 50.0)
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
