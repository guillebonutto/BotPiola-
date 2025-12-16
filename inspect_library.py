import inspect
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync

try:
    with open("inspection_result_full.txt", "w") as f:
        for name, member in inspect.getmembers(PocketOptionAsync):
            if not name.startswith("__"):
                f.write(f"Member: {name}\n")
                if inspect.isfunction(member) or inspect.ismethod(member):
                     try:
                        sig = inspect.signature(member)
                        f.write(f"  Signature: {sig}\n")
                        f.write(f"  Docstring: {member.__doc__}\n")
                     except:
                        pass
except Exception as e:
    with open("inspection_result_full.txt", "w") as f:
        f.write(f"Error inspecting: {e}")
