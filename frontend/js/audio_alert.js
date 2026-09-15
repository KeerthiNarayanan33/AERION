/**
 * Tactical Web Audio API Synthesizer & Military Acoustic Warning Engine
 * Generates acoustic alarms, sirens, and synthesized vocal warnings locally.
 * Part of SIH 2026 Border Surveillance Prototype (Phase 10 & 20).
 */
class TacticalAudioAlert {
    constructor() {
        this.ctx = null;
        this.muted = localStorage.getItem('sih_audio_muted') === 'true';
        this.volume = 0.75;
        this.alarmInterval = null;
        this._speechUnlocked = false;
        this._isAudioUnlocked = false;
        this._activeAlarmLoop = null;

        // Auto-attach user gesture listeners to unlock browser audio autoplay
        this._bindUserGestureUnlock();
    }

    _bindUserGestureUnlock() {
        const unlockHandler = () => {
            this.unlockAudio();
        };

        if (typeof window !== 'undefined') {
            ['click', 'pointerdown', 'keydown', 'touchstart'].forEach(evt => {
                window.addEventListener(evt, unlockHandler, { passive: true });
            });
        }
    }

    _initContext() {
        if (!this.ctx) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (AudioCtx) {
                this.ctx = new AudioCtx();
            }
        }
        if (this.ctx && this.ctx.state === 'suspended') {
            this.ctx.resume().then(() => {
                this._isAudioUnlocked = true;
                this._dispatchStateChange();
            }).catch(e => {
                console.debug('[AUDIO] AudioContext resume deferred:', e);
            });
        } else if (this.ctx && this.ctx.state === 'running') {
            this._isAudioUnlocked = true;
        }
    }

    unlockAudio() {
        this._initContext();
        if (this.ctx && this.ctx.state === 'suspended') {
            this.ctx.resume().catch(() => {});
        }
        this._isAudioUnlocked = true;

        // Prime speech synthesis with a zero-volume syllable
        if ('speechSynthesis' in window && !this._speechUnlocked) {
            try {
                window.speechSynthesis.resume();
                const prime = new SpeechSynthesisUtterance(' ');
                prime.volume = 0.01;
                window.speechSynthesis.speak(prime);
                this._speechUnlocked = true;
            } catch (e) {
                console.debug('[VOICE] Speech unlock deferred:', e);
            }
        }

        this._dispatchStateChange();
    }

    _dispatchStateChange() {
        if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('tactical-audio-state-changed', {
                detail: {
                    muted: this.muted,
                    unlocked: this._isAudioUnlocked,
                    state: this.ctx ? this.ctx.state : 'uninitialized'
                }
            }));
        }
    }

    isMuted() {
        return this.muted;
    }

    setMuted(mute) {
        this.muted = !!mute;
        localStorage.setItem('sih_audio_muted', this.muted);
        if (this.muted) {
            this.stopAlarm();
        }
        this._dispatchStateChange();
        return this.muted;
    }

    toggleMute() {
        this.unlockAudio();
        const newMute = this.setMuted(!this.muted);
        if (!newMute) {
            // Play confirmation chirp
            this.playRadarBlip();
        }
        return newMute;
    }

    /**
     * Short high-pitch radar contact chirp
     */
    playRadarBlip() {
        if (this.muted) return;
        try {
            this._initContext();
            if (!this.ctx) return;

            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            const now = this.ctx.currentTime;

            osc.type = 'sine';
            osc.frequency.setValueAtTime(950, now);
            osc.frequency.exponentialRampToValueAtTime(1750, now + 0.08);

            gain.gain.setValueAtTime(this.volume * 0.45, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.start(now);
            osc.stop(now + 0.09);
        } catch (e) {
            console.debug('[AUDIO] Blip error:', e);
        }
    }

    /**
     * Warning sector entry beep
     */
    playWarningBeep() {
        if (this.muted) return;
        try {
            this._initContext();
            if (!this.ctx) return;

            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            const now = this.ctx.currentTime;

            osc.type = 'triangle';
            osc.frequency.setValueAtTime(659.25, now); // E5

            gain.gain.setValueAtTime(this.volume * 0.7, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.start(now);
            osc.stop(now + 0.22);
        } catch (e) {
            console.debug('[AUDIO] Warning error:', e);
        }
    }

    /**
     * Urgent high-penetration perimeter breach siren (military alternating warble)
     */
    playCriticalAlarm(repeatCount = 5) {
        if (this.muted) return;
        try {
            this.unlockAudio();
            if (!this.ctx) return;

            let cycle = 0;
            const stepAlarm = () => {
                if (this.muted || cycle >= repeatCount * 2) return;
                try {
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    const now = this.ctx.currentTime;

                    // Alternating dual-frequency warble: 960Hz to 640Hz
                    const freq = (cycle % 2 === 0) ? 960 : 640;
                    osc.type = 'sawtooth';
                    osc.frequency.setValueAtTime(freq, now);

                    gain.gain.setValueAtTime(this.volume * 0.85, now);
                    gain.gain.exponentialRampToValueAtTime(0.02, now + 0.15);

                    osc.connect(gain);
                    gain.connect(this.ctx.destination);

                    osc.start(now);
                    osc.stop(now + 0.16);
                    cycle++;
                    setTimeout(stepAlarm, 170);
                } catch (err) {
                    console.debug('[AUDIO] Alarm cycle error:', err);
                }
            };
            stepAlarm();
        } catch (e) {
            console.debug('[AUDIO] Critical alarm error:', e);
        }
    }

    /**
     * Announces unauthorized person detection at a specific zone with siren and voice alert.
     * Required alert format: "Unauthorised person detected at zone <zone_name>"
     */
    announceUnauthorizedPerson(zoneName = "Sector Charlie") {
        if (this.muted) return;
        this.unlockAudio();
        this.playCriticalAlarm(4);
        setTimeout(() => {
            this.speakTacticalAlert(`Unauthorised person detected at zone ${zoneName}`);
        }, 300);
    }

    /**
     * Starts continuous looping alarm for active restricted breaches.
     * Repeats every 2.8 seconds until explicitly stopped with stopAlarm().
     */
    startContinuousAlarm(zoneLabel = "Sector Charlie") {
        if (this.muted) return;
        this.stopAlarm();

        console.warn(`[AUDIO] Starting continuous acoustic alarm for ${zoneLabel}`);
        this.playCriticalAlarm(5);
        this.speakTacticalAlert(`Unauthorised person detected at zone ${zoneLabel}`);

        this._activeAlarmLoop = setInterval(() => {
            if (this.muted) {
                this.stopAlarm();
                return;
            }
            this.playCriticalAlarm(4);
        }, 2800);
    }


    /**
     * Stops continuous alarm siren
     */
    stopAlarm() {
        if (this._activeAlarmLoop) {
            clearInterval(this._activeAlarmLoop);
            this._activeAlarmLoop = null;
        }
        if (this.alarmInterval) {
            clearInterval(this.alarmInterval);
            this.alarmInterval = null;
        }
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
    }

    /**
     * Autonomous UAV dispatch sonar ping
     */
    playUAVDispatchPing() {
        if (this.muted) return;
        try {
            this._initContext();
            if (!this.ctx) return;

            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            const now = this.ctx.currentTime;

            osc.type = 'sine';
            osc.frequency.setValueAtTime(1174.66, now); // D6
            osc.frequency.exponentialRampToValueAtTime(880, now + 0.4);

            gain.gain.setValueAtTime(this.volume * 0.75, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.start(now);
            osc.stop(now + 0.5);
        } catch (e) {
            console.debug('[AUDIO] UAV ping error:', e);
        }
    }

    /**
     * Synthesizes offline military voice announcement via Web Speech API (Phase 12 & 20).
     */
    speakTacticalAlert(text) {
        if (this.muted) return;
        if (!('speechSynthesis' in window)) return;

        try {
            window.speechSynthesis.cancel();
            window.speechSynthesis.resume();

            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 1.05;
            utterance.pitch = 0.95;
            utterance.volume = Math.min(1.0, this.volume * 1.3);

            const voices = window.speechSynthesis.getVoices();
            const preferred = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('David') || v.name.includes('Male') || v.name.includes('Google UK English Male')));
            if (preferred) utterance.voice = preferred;

            window.speechSynthesis.speak(utterance);
        } catch (e) {
            console.debug('[VOICE] Speech synthesis error:', e);
        }
    }

    /**
     * Tests both acoustic siren and synthesized voice
     */
    testAlarm() {
        this.unlockAudio();
        this.playCriticalAlarm(3);
        setTimeout(() => {
            this.speakTacticalAlert("Acoustic siren check. Tactical audio armed and functional.");
        }, 600);
    }
}

// Global audio alert singleton
window.audioAlert = new TacticalAudioAlert();
