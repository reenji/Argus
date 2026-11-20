"""sounddevice, imported (with its PortAudio library) on first use."""


class _LazySoundDevice:
    """Imports sounddevice (and its PortAudio library) on first use.

    Only the desktop microphone and speaker paths need it, so the hosted API
    and the test suite run on machines without an audio stack.
    """

    def __getattr__(self, name):
        import sounddevice

        return getattr(sounddevice, name)


sd = _LazySoundDevice()
