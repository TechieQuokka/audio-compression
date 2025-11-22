"""
Dynamic Range Compressor
순수 Python/NumPy 구현
"""

import numpy as np
from scipy import signal


class DynamicRangeCompressor:
    """
    다이나믹 레인지 압축기

    Parameters:
        threshold (float): 압축 시작 레벨 (dB), 기본 -20
        ratio (float): 압축 비율, 기본 3.0 (3:1)
        attack (float): 압축 시작 시간 (ms), 기본 5
        release (float): 압축 해제 시간 (ms), 기본 50
        knee (float): Soft knee 크기 (dB), 기본 3
        sample_rate (int): 샘플레이트 (Hz), 기본 44100
    """

    def __init__(
        self,
        threshold=-20.0,
        ratio=3.0,
        attack=5.0,
        release=50.0,
        knee=3.0,
        sample_rate=44100
    ):
        self.threshold = threshold
        self.ratio = ratio
        self.attack = attack
        self.release = release
        self.knee = knee
        self.sample_rate = sample_rate

        # Attack/Release 계수 계산 (ms -> samples -> coefficient)
        self.attack_coef = np.exp(-1.0 / (self.sample_rate * self.attack / 1000.0))
        self.release_coef = np.exp(-1.0 / (self.sample_rate * self.release / 1000.0))

    def _db_to_linear(self, db):
        """dB를 선형 스케일로 변환"""
        return 10.0 ** (db / 20.0)

    def _linear_to_db(self, linear):
        """선형 스케일을 dB로 변환"""
        return 20.0 * np.log10(np.maximum(linear, 1e-10))

    def _rms_envelope(self, audio, window_size=512):
        """
        RMS 기반 envelope detection

        Args:
            audio: 입력 오디오 신호
            window_size: RMS 계산 윈도우 크기

        Returns:
            RMS envelope (dB)
        """
        # 제곱 계산
        squared = audio ** 2

        # 이동 평균 필터로 RMS 계산
        window = np.ones(window_size) / window_size
        rms = np.sqrt(np.convolve(squared, window, mode='same'))

        # dB로 변환
        rms_db = self._linear_to_db(rms)

        return rms_db

    def _compute_gain_reduction(self, level_db):
        """
        Gain reduction 계산 (Soft Knee)

        Args:
            level_db: 입력 레벨 (dB)

        Returns:
            Gain reduction (dB, 항상 0 이하)
        """
        # Soft knee 범위 계산
        knee_start = self.threshold - self.knee / 2.0
        knee_end = self.threshold + self.knee / 2.0

        gain_reduction = np.zeros_like(level_db)

        # 1. Threshold 미만: 압축 없음
        below_knee = level_db < knee_start
        gain_reduction[below_knee] = 0.0

        # 2. Knee 영역: 부드러운 전환
        in_knee = (level_db >= knee_start) & (level_db <= knee_end)
        if np.any(in_knee):
            # 2차 곡선으로 부드러운 전환
            knee_input = level_db[in_knee] - knee_start
            knee_output = knee_input ** 2 / (2.0 * self.knee)
            gain_reduction[in_knee] = -(knee_output * (1.0 / self.ratio - 1.0))

        # 3. Threshold 초과: 전체 압축
        above_knee = level_db > knee_end
        if np.any(above_knee):
            overshoot = level_db[above_knee] - self.threshold
            gain_reduction[above_knee] = -overshoot * (1.0 - 1.0 / self.ratio)

        return gain_reduction

    def _apply_attack_release(self, gain_reduction):
        """
        Attack/Release time으로 smooth transition

        Args:
            gain_reduction: 목표 gain reduction (dB)

        Returns:
            Smoothed gain reduction (dB)
        """
        smoothed = np.zeros_like(gain_reduction)
        state = 0.0

        for i in range(len(gain_reduction)):
            target = gain_reduction[i]

            # Attack (gain reduction이 증가할 때, 즉 더 압축)
            if target < state:
                coef = self.attack_coef
            # Release (gain reduction이 감소할 때, 즉 덜 압축)
            else:
                coef = self.release_coef

            # Exponential smoothing
            state = target + coef * (state - target)
            smoothed[i] = state

        return smoothed

    def compress(self, audio):
        """
        오디오에 다이나믹 레인지 압축 적용

        Args:
            audio: 입력 오디오 (numpy array, mono 또는 stereo)

        Returns:
            압축된 오디오 (같은 shape)
        """
        # Mono/Stereo 처리
        is_mono = audio.ndim == 1
        if is_mono:
            audio = audio.reshape(-1, 1)

        compressed = np.zeros_like(audio)

        # 각 채널 독립 처리
        for ch in range(audio.shape[1]):
            channel = audio[:, ch]

            # 1. RMS envelope 계산
            level_db = self._rms_envelope(channel)

            # 2. Gain reduction 계산
            gain_reduction = self._compute_gain_reduction(level_db)

            # 3. Attack/Release 적용
            smooth_gain_reduction = self._apply_attack_release(gain_reduction)

            # 4. dB -> 선형 gain으로 변환
            gain_linear = self._db_to_linear(smooth_gain_reduction)

            # 5. 오디오에 적용
            compressed[:, ch] = channel * gain_linear

        # Mono였으면 다시 1D로
        if is_mono:
            compressed = compressed.flatten()

        return compressed

    def get_stats(self, audio, compressed):
        """
        압축 전후 통계 계산

        Args:
            audio: 원본 오디오
            compressed: 압축된 오디오

        Returns:
            dict: 통계 정보
        """
        # Mono로 변환
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        if compressed.ndim > 1:
            compressed = np.mean(compressed, axis=1)

        # RMS 레벨 계산
        original_rms = np.sqrt(np.mean(audio ** 2))
        compressed_rms = np.sqrt(np.mean(compressed ** 2))

        # Peak 레벨 계산
        original_peak = np.max(np.abs(audio))
        compressed_peak = np.max(np.abs(compressed))

        # 다이나믹 레인지 계산 (간이 계산: peak - RMS)
        original_dr = self._linear_to_db(original_peak) - self._linear_to_db(original_rms)
        compressed_dr = self._linear_to_db(compressed_peak) - self._linear_to_db(compressed_rms)

        return {
            'original_rms_db': self._linear_to_db(original_rms),
            'compressed_rms_db': self._linear_to_db(compressed_rms),
            'original_peak_db': self._linear_to_db(original_peak),
            'compressed_peak_db': self._linear_to_db(compressed_peak),
            'original_dynamic_range_db': original_dr,
            'compressed_dynamic_range_db': compressed_dr,
            'gain_reduction_db': self._linear_to_db(compressed_rms) - self._linear_to_db(original_rms)
        }
