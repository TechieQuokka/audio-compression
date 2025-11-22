"""
LUFS (Loudness Units relative to Full Scale) Meter
ITU-R BS.1770-4 표준 기반
"""

import numpy as np
import pyloudnorm as pyln


class LUFSMeter:
    """
    LUFS 측정 및 정규화

    Parameters:
        sample_rate (int): 샘플레이트 (Hz), 기본 44100
        target_lufs (float): 목표 LUFS 레벨, 기본 -16.0 (방송 표준)
    """

    def __init__(self, sample_rate=44100, target_lufs=-16.0):
        self.sample_rate = sample_rate
        self.target_lufs = target_lufs
        self.meter = pyln.Meter(sample_rate)

    def measure_lufs(self, audio):
        """
        오디오의 Integrated LUFS 측정

        Args:
            audio: 입력 오디오 (numpy array, mono 또는 stereo)

        Returns:
            float: Integrated LUFS 값
        """
        # Mono를 stereo로 변환 (pyloudnorm은 최소 1D 필요)
        if audio.ndim == 1:
            audio_for_meter = audio
        else:
            # Stereo면 그대로 사용
            audio_for_meter = audio

        # LUFS 측정
        loudness = self.meter.integrated_loudness(audio_for_meter)

        return loudness

    def calculate_makeup_gain(self, current_lufs):
        """
        목표 LUFS에 도달하기 위한 makeup gain 계산

        Args:
            current_lufs: 현재 LUFS 레벨

        Returns:
            float: 필요한 gain (dB)
        """
        # LUFS는 dB 단위이므로 직접 차이 계산
        makeup_gain = self.target_lufs - current_lufs

        return makeup_gain

    def normalize_to_target(self, audio, current_lufs=None):
        """
        오디오를 목표 LUFS로 정규화

        Args:
            audio: 입력 오디오
            current_lufs: 현재 LUFS (None이면 자동 측정)

        Returns:
            tuple: (정규화된 오디오, makeup gain dB)
        """
        # LUFS 측정 (제공되지 않았으면)
        if current_lufs is None:
            current_lufs = self.measure_lufs(audio)

        # Makeup gain 계산
        makeup_gain_db = self.calculate_makeup_gain(current_lufs)

        # dB를 선형 gain으로 변환
        makeup_gain_linear = 10.0 ** (makeup_gain_db / 20.0)

        # Gain 적용
        normalized = audio * makeup_gain_linear

        # Peak clipping 방지 (0dBFS 제한)
        peak = np.max(np.abs(normalized))
        if peak > 1.0:
            # Peak limiter: 1.0을 넘으면 전체를 줄임
            normalized = normalized / peak
            actual_gain_db = makeup_gain_db - 20.0 * np.log10(peak)
            print(f"⚠️  Warning: Peak limiting applied ({peak:.2f} -> 1.0)")
            print(f"   Actual gain: {actual_gain_db:.2f} dB (requested: {makeup_gain_db:.2f} dB)")
        else:
            actual_gain_db = makeup_gain_db

        return normalized, actual_gain_db

    def get_loudness_stats(self, audio):
        """
        오디오의 라우드니스 통계 계산

        Args:
            audio: 입력 오디오

        Returns:
            dict: 통계 정보
        """
        # Integrated LUFS
        integrated = self.measure_lufs(audio)

        # Peak 레벨 (dBTP - True Peak)
        peak_linear = np.max(np.abs(audio))
        peak_db = 20.0 * np.log10(peak_linear) if peak_linear > 0 else -np.inf

        # RMS 레벨
        rms_linear = np.sqrt(np.mean(audio ** 2))
        rms_db = 20.0 * np.log10(rms_linear) if rms_linear > 0 else -np.inf

        # Crest factor (peak / RMS)
        crest_factor_db = peak_db - rms_db

        # 목표 LUFS 대비 차이
        lufs_difference = integrated - self.target_lufs

        return {
            'integrated_lufs': integrated,
            'peak_db': peak_db,
            'rms_db': rms_db,
            'crest_factor_db': crest_factor_db,
            'target_lufs': self.target_lufs,
            'lufs_difference': lufs_difference,
            'required_makeup_gain': -lufs_difference
        }

    def analyze_dynamic_range(self, audio, window_size=3.0):
        """
        다이나믹 레인지 분석 (Loudness Range - LRA)

        Args:
            audio: 입력 오디오
            window_size: 분석 윈도우 크기 (초)

        Returns:
            float: LRA (Loudness Range) in LU
        """
        # 윈도우 샘플 수
        window_samples = int(window_size * self.sample_rate)

        # 전체 오디오를 윈도우로 분할
        num_windows = len(audio) // window_samples
        loudness_per_window = []

        for i in range(num_windows):
            start = i * window_samples
            end = start + window_samples
            window = audio[start:end]

            try:
                loudness = self.meter.integrated_loudness(window)
                if not np.isnan(loudness) and not np.isinf(loudness):
                    loudness_per_window.append(loudness)
            except:
                pass

        if len(loudness_per_window) < 2:
            return 0.0

        # LRA 계산: 10th percentile과 95th percentile의 차이
        loudness_array = np.array(loudness_per_window)
        p10 = np.percentile(loudness_array, 10)
        p95 = np.percentile(loudness_array, 95)
        lra = p95 - p10

        return lra
