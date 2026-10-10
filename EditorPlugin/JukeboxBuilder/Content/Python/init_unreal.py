# Unreal runs this automatically when the editor starts (Python Editor Script Plugin).
import unreal

try:
    import jukebox_editor
    jukebox_editor.startup()
except Exception as e:  # never break editor startup
    unreal.log_error("Jukebox Builder failed to start: {}".format(e))
