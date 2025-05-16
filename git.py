import subprocess

def run_git_commands():
    print("💬 Enter your commit message:")
    commit_message = input("> ").strip()

    if not commit_message:
        print("❌ Commit message cannot be empty.")
        return

    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Changes pushed to GitHub successfully!")
    except subprocess.CalledProcessError as e:
        print("❌ An error occurred:", e)

if __name__ == "__main__":
    run_git_commands()
