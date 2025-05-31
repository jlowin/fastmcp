import multiprocessing

if hasattr(multiprocessing, "get_all_start_methods"):
    if "forkserver" in multiprocessing.get_all_start_methods():
        multiprocessing.set_start_method("forkserver", force=True)
