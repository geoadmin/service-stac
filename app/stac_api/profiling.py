import cProfile
import functools
import io
import os
import pstats


def profiling(function_to_profile):
    ''''Profiling wrapper for debugging

    You can use this wrapper to get some profiling data on the function. The profiling data are
    printed in the console.
    '''

    @functools.wraps(function_to_profile)
    def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()

        profiler.enable()
        return_value = function_to_profile(*args, **kwargs)
        profiler.disable()

        stream = io.StringIO()
        stats = pstats.Stats(profiler,
                             stream=stream).sort_stats(os.getenv('PROFILING_SORT_KEY', 'cumtime'))
        stats_lines = os.getenv('PROFILING_STATS_LINES', None)
        if stats_lines:
            stats.print_stats(stats_lines)
        else:
            stats.print_stats()

        return return_value

    return wrapper
