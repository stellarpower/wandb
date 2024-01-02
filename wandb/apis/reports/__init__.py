# flake8: noqa
import os


if os.getenv("WANDB_REPORT_API_ENABLE_V2"):
    from wandb.apis.reports2 import *

else:
    # Use legacy report api
    from inspect import cleandoc

    from ... import termwarn
    from . import blocks, helpers, panels, templates
    from .blocks import *
    from .helpers import LineKey, PCColumn
    from .panels import *
    from .report import Report
    from .runset import Runset
    from .templates import *
    from .util import InlineCode, InlineLaTeX, Link

    def show_welcome_message():
        if os.getenv("WANDB_REPORT_API_DISABLE_MESSAGE"):
            return

        termwarn(
            cleandoc(
                """
                The v1 API is deprecated and will be removed in a future release.  Please move to v2 by setting the env var WANDB_REPORT_API_ENABLE_V2=True.  This will be on by default in a future release.
                You can disable this message by setting the env var WANDB_REPORT_API_DISABLE_MESSAGE=True
                """
            )
        )

    show_welcome_message()
