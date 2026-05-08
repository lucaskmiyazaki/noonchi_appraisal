(function () {
  'use strict';

  function createMeetingWidgetArousalMonitor(onArousal) {
    let audioContext = null;
    let audioSource = null;
    let audioAnalyser = null;
    let audioLevelData = null;
    let audioMonitorRaf = null;

    let audioNoiseFloor = 0;
    let audioSpeechFloor = 0;
    let audioActiveFrames = 0;

    function stop() {
      if (audioMonitorRaf) {
        window.cancelAnimationFrame(audioMonitorRaf);
        audioMonitorRaf = null;
      }

      if (audioSource) {
        try { audioSource.disconnect(); } catch (_) {}
        audioSource = null;
      }

      if (audioAnalyser) {
        try { audioAnalyser.disconnect(); } catch (_) {}
        audioAnalyser = null;
      }

      if (audioContext) {
        try { audioContext.close(); } catch (_) {}
        audioContext = null;
      }

      audioLevelData = null;
      audioNoiseFloor = 0;
      audioSpeechFloor = 0;
      audioActiveFrames = 0;
    }

    function start(stream) {
      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextCtor || !stream) {
        return false;
      }

      stop();

      const ctx = new AudioContextCtor();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.6;
      source.connect(analyser);

      audioContext = ctx;
      audioSource = source;
      audioAnalyser = analyser;
      audioLevelData = new Float32Array(analyser.fftSize);

      const tick = () => {
        if (!audioAnalyser || !audioLevelData) {
          return;
        }

        audioAnalyser.getFloatTimeDomainData(audioLevelData);

        let sum = 0;
        for (let i = 0; i < audioLevelData.length; i++) {
          const sample = audioLevelData[i];
          sum += sample * sample;
        }

        const rms = Math.sqrt(sum / audioLevelData.length);
        const speechGate = 0.028;

        if (rms < speechGate) {
          audioNoiseFloor = audioNoiseFloor
            ? (audioNoiseFloor * 0.985 + rms * 0.015)
            : rms;
        }

        if (rms >= speechGate) {
          audioSpeechFloor = audioSpeechFloor
            ? (audioSpeechFloor * 0.96 + rms * 0.04)
            : rms;
        }

        const noiseFloor = audioNoiseFloor || 0.01;
        const speechFloor = audioSpeechFloor || 0.03;

        const threshold = Math.max(
          0.06,
          noiseFloor * 4.2,
          speechFloor * 1.85
        );

        const isElevated = rms > threshold;

        if (isElevated) {
          audioActiveFrames += 1;
        } else {
          audioActiveFrames = Math.max(0, audioActiveFrames - 1);
        }

        if (audioActiveFrames >= 10) {
          if (typeof onArousal === 'function') {
            onArousal();
          }
          audioActiveFrames = 0;
        }

        audioMonitorRaf = window.requestAnimationFrame(tick);
      };

      audioMonitorRaf = window.requestAnimationFrame(tick);
      return true;
    }

    return { start: start, stop: stop };
  }

  window.createMeetingWidgetArousalMonitor = createMeetingWidgetArousalMonitor;
})();
