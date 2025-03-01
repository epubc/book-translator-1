## Installation

These instructions assume you have Python 3 and `pip` installed.  If not, please install them first.  The specific Python version required is not evident from the provided information, but Python 3.7+ is a reasonable assumption.  **It is highly recommended to use a virtual environment to manage project dependencies.**

1.  **Clone the Repository (Optional):**

    ```bash
    git clone https://github.com/rl1809/book-translator.git
    cd book-translator
    ```

2.  **Create a Virtual Environment:**

    It's best practice to create a virtual environment to isolate the project's dependencies.  This prevents conflicts with other Python projects on your system.

    ```bash
    python3 -m venv .venv
    ```

3.  **Activate the Virtual Environment:**

    Before installing dependencies or running the project, you need to *activate* the virtual environment.  The activation command depends on your operating system:

    *   **On Windows (Command Prompt):**
        ```bash
        .venv\Scripts\activate.bat
        ```

    *   **On Windows (PowerShell):**
        ```powershell
        .venv\Scripts\Activate.ps1
        ```

    *   **On macOS and Linux:**
        ```bash
        source .venv/bin/activate
        ```

4.  **Install Dependencies:**

    Now that the virtual environment is active, install the project's dependencies using `pip`:

    ```bash
    pip install -r requirements.txt
    ```
     If the command above fails, it might be because `pip` is not correctly configured for your Python 3 installation.  Try these alternatives:

    ```bash
    python3 -m pip install -r requirements.txt
    # or, on some systems:
    pip3 install -r requirements.txt
    ```

## Running the Application

With the virtual environment activated and dependencies installed, you can launch the application's user interface:

```bash
python __main__.py
