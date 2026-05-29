# File Lister 📁

A powerful, feature-rich command-line tool for listing, analyzing, and exploring file systems with comprehensive filtering, formatting, and search capabilities.

## Features ✨

- **Multiple Listing Modes**: List files, display directory trees, view summaries, search, and find duplicates
- **Advanced Filtering**: Filter by extension, size, pattern, type, and hidden files
- **Recursive Traversal**: Explore directories recursively with depth control
- **Rich Statistics**: Get detailed file statistics including size, permissions, and timestamps
- **Multiple Output Formats**: Beautiful terminal output, JSON for automation, and tabular formats
- **Smart Icons**: Visual file type indicators with emoji support
- **Duplicate Detection**: Find duplicate files by name or size
- **Pattern Search**: Search files using regular expressions
- **Summary Analytics**: Get directory statistics with size distribution and extension counts

## Installation 📦

### Prerequisites

- Node.js 18.0.0 or higher

### Setup

1. Clone or navigate to the project directory:
```bash
cd file-lister
```

2. Install dependencies:
```bash
npm install
```

3. (Optional) Install globally for system-wide access:
```bash
npm install -g .
```

## Usage 🚀

### Basic Usage

List files in the current directory:
```bash
npm start
```

List files in a specific directory:
```bash
npm start /path/to/directory
```

### Commands

#### `list` - List Files

List all files with various filtering options:
```bash
npm start list [directory] [options]
```

**Options:**
- `-r, --recursive` - List files recursively
- `-d, --depth <number>` - Maximum depth for recursive listing (default: 10)
- `-e, --extensions <extensions>` - Filter by file extensions (comma-separated)
- `-p, --pattern <pattern>` - Filter by regex pattern
- `--min-size <size>` - Minimum file size (e.g., 1KB, 1MB, 1GB)
- `--max-size <size>` - Maximum file size (e.g., 1KB, 1MB, 1GB)
- `-t, --type <type>` - Filter by type: files, directories, or all (default: all)
- `-a, --all` - Include hidden files
- `--stats` - Include file statistics
- `--json` - Output in JSON format
- `--relative` - Show relative paths

**Examples:**

List all JavaScript files recursively:
```bash
npm start list . -r -e js
```

List files larger than 1MB with statistics:
```bash
npm start list . --min-size 1MB --stats
```

Find all JSON files in a specific directory:
```bash
npm start list /path/to/dir -e json
```

#### `tree` - Display Directory Tree

Display a visual tree structure of directories:
```bash
npm start tree [directory] [options]
```

**Options:**
- `-d, --depth <number>` - Maximum depth to display (default: 5)
- `-e, --extensions <extensions>` - Filter by file extensions
- `-a, --all` - Include hidden files
- `--json` - Output in JSON format

**Examples:**

Show directory tree up to 3 levels deep:
```bash
npm start tree . -d 3
```

Show tree with only TypeScript files:
```bash
npm start tree . -e ts
```

#### `summary` - Display Directory Statistics

Get comprehensive statistics about a directory:
```bash
npm start summary [directory] [options]
```

**Options:**
- `-r, --recursive` - Analyalyze recursively (default: true)
- `-e, --extensions <extensions>` - Filter by file extensions
- `--json` - Output in JSON format

**Examples:**

Get summary statistics:
```bash
npm start summary .
```

Get summary for only image files:
```bash
npm start summary . -e png,jpg,jpeg,gif,svg
```

#### `search` - Search Files by Pattern

Search for files matching a regex pattern:
```bash
npm start search <pattern> [directory] [options]
```

**Options:**
- `-r, --recursive` - Search recursively (default: true)
- `-i, --case-sensitive` - Case-sensitive search
- `--json` - Output in JSON format

**Examples:**

Search for files containing "test":
```bash
npm start search "test"
```

Search for files ending with ".config.js":
```bash
npm start search "\.config\.js$"
```

#### `duplicates` - Find Duplicate Files

Find duplicate files by name or size:
```bash
npm start duplicates [directory] [options]
```

**Options:**
- `-r, --recursive` - Search recursively (default: true)
- `--by-size` - Group by size instead of name
- `--json` - Output in JSON format

**Examples:**

Find duplicates by filename:
```bash
npm start duplicates .
```

Find potential duplicates by size:
```bash
npm start duplicates . --by-size
```

## Output Examples 📊

### File List Output
```
📂 Directory: /Users/username/projects
Found 15 item(s)

Name │ Type │ Size │ Modified │ Path
══════════════════════════════════════════════════════════════════════
📁 src │ DIR │ - │ 2024-01-15 │ src
📜 index.js │ FILE │ 2.5 KB │ 2024-01-15 │ index.js
📄 README.md │ FILE │ 4.1 KB │ 2024-01-14 │ README.md
```

### Tree Output
```
📂 /Users/username/projects
└── 📁 src
    ├── 📜 index.js
    ├── 📜 cli.js
    └── 📁 utils
        ├── 📜 helpers.js
        └── 📜 validators.js
```

### Summary Output
```
📊 Directory Summary: /Users/username/projects

Overview:
  Total Items: 150
  Files: 120
  Directories: 30
  Total Size: 2.5 MB
  Average File Size: 21.5 KB

Size Extremes:
  Largest: package-lock.json (1.2 MB)
  Smallest: .gitignore (125 B)

File Size Distribution:
  Small (< 1MB): 118
  Medium (1-100MB): 2
  Large (100MB-1GB): 0
  Extra Large (> 1GB): 0

Top File Extensions:
  .js    45 (37.5%)
  .json  12 (10.0%)
  .md    8 (6.7%)
```

## Development 🔧

### Project Structure

```
file-lister/
├── src/
│   ├── index.js       # Core functionality
│   └── cli.js         # CLI interface
├── package.json
└── README.md
```

### Core Functions

The tool provides several programmatic functions:

- `listFiles(dirPath, options)` - List files with filtering
- `getDirectoryTree(dirPath, options)` - Get tree structure
- `getDirectorySummary(dirPath, options)` - Get statistics
- `searchFiles(dirPath, pattern, options)` - Search by pattern
- `findDuplicates(dirPath, options)` - Find duplicates
- `formatFileSize(bytes)` - Format bytes to readable string

### Testing

Run the test suite:
```bash
npm test
```

## Tips & Tricks 💡

1. **Quick size analysis**: Use `summary` to understand directory composition
2. **Clean up duplicates**: Use `duplicates` to identify repeated files
3. **Find large files**: Combine `list` with `--min-size` to find space hogs
4. **JSON automation**: Use `--json` flag for scripting and automation
5. **Specific file types**: Use `-e` to focus on specific file types

## Troubleshooting 🔍

### Permission Errors
Some directories may require elevated permissions. Use `sudo` if necessary:
```bash
sudo npm start list /protected/directory
```

### Large Directories
For very large directories, consider using `--depth` to limit recursion:
```bash
npm start list . -r -d 2
```

### Memory Issues
When processing extremely large directory trees, the tool uses streaming to minimize memory usage.

## License 📄

MIT License - See LICENSE file for details

## Contributing 🤝

Contributions are welcome! Please feel free to submit a Pull Request.

## Author 👤

Created with care for developers who need powerful file system tools.
