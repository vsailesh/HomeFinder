#!/usr/bin/env node

/**
 * File Lister - CLI Interface
 * A comprehensive command-line tool for listing and analyzing files
 */

import { Command } from 'commander';
import chalk from 'chalk';
import path from 'path';
import fs from 'fs';
import {
  listFiles,
  getDirectoryTree,
  getDirectorySummary,
  searchFiles,
  findDuplicates,
  formatFileSize,
} from './index.js';

const program = new Command();

// ASCII Art Banner
const banner = `
${chalk.cyan.bold('╔═══════════════════════════════════════╗')}
${chalk.cyan.bold('║')}   ${chalk.white.bold('File Lister v1.0.0')}             ${chalk.cyan.bold('║')}
${chalk.cyan.bold('║')}   ${chalk.gray('Advanced File System Explorer')}  ${chalk.cyan.bold('║')}
${chalk.cyan.bold('╚═══════════════════════════════════════╝')}
`;

// Utility function to format output tables
function formatTable(headers, rows, maxWidth = 120) {
  const columnWidths = headers.map((header, index) => {
    const maxContentWidth = Math.max(
      header.length,
      ...rows.map(row => String(row[index]).length)
    );
    return Math.min(maxContentWidth + 2, maxWidth);
  });

  const separator = columnWidths.map(width => '─'.repeat(width)).join('┼');

  let output = '';

  // Header row
  output += columnWidths.map((width, index) =>
    headers[index].padEnd(width)
  ).join('│') + '\n';

  output += separator + '\n';

  // Data rows
  for (const row of rows) {
    output += columnWidths.map((width, index) => {
      let cell = String(row[index] || '');
      if (cell.length > width - 2) {
        cell = cell.substring(0, width - 5) + '...';
      }
      return cell.padEnd(width);
    }).join('│') + '\n';
  }

  return output;
}

// Utility function to format file type icons
function getFileIcon(file) {
  if (file.isDirectory) {
    return chalk.blue('📁');
  }
  if (file.isSymbolicLink) {
    return chalk.cyan('🔗');
  }

  // File extension icons
  const ext = file.extension || '';
  const iconMap = {
    'js': chalk.yellow('📜'),
    'ts': chalk.blue('📜'),
    'py': chalk.green('🐍'),
    'java': chalk.red('☕'),
    'html': chalk.hex('#FFA500')('🌐'),
    'css': chalk.blue('🎨'),
    'json': chalk.yellow('📋'),
    'md': chalk.white('📝'),
    'txt': chalk.white('📄'),
    'png': chalk.magenta('🖼️'),
    'jpg': chalk.magenta('🖼️'),
    'jpeg': chalk.magenta('🖼️'),
    'gif': chalk.magenta('🖼️'),
    'svg': chalk.magenta('🎨'),
    'pdf': chalk.red('📕'),
    'zip': chalk.yellow('📦'),
    'tar': chalk.yellow('📦'),
    'gz': chalk.yellow('📦'),
  };

  return iconMap[ext] || chalk.white('📄');
}

// List command
program
  .command('list [directory]')
  .description('List all files in a directory')
  .option('-r, --recursive', 'List files recursively')
  .option('-d, --depth <number>', 'Maximum depth for recursive listing', '10')
  .option('-e, --extensions <extensions>', 'Filter by file extensions (comma-separated)')
  .option('-p, --pattern <pattern>', 'Filter by regex pattern')
  .option('--min-size <size>', 'Minimum file size (e.g., 1KB, 1MB, 1GB)')
  .option('--max-size <size>', 'Maximum file size (e.g., 1KB, 1MB, 1GB)')
  .option('-t, --type <type>', 'Filter by type: files, directories, or all', 'all')
  .option('-a, --all', 'Include hidden files')
  .option('--stats', 'Include file statistics')
  .option('--json', 'Output in JSON format')
  .option('--relative', 'Show relative paths')
  .action((directory = '.', options) => {
    console.log(banner);

    const dirPath = path.resolve(directory);

    // Validate directory
    if (!fs.existsSync(dirPath)) {
      console.error(chalk.red(`✖ Error: Directory not found: ${dirPath}`));
      process.exit(1);
    }

    // Parse size filters
    const parseSize = (sizeStr) => {
      if (!sizeStr) return undefined;
      const units = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, TB: 1024 ** 4 };
      const match = sizeStr.match(/^(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)?$/i);
      if (match) {
        const value = parseFloat(match[1]);
        const unit = (match[2] || 'B').toUpperCase();
        return value * units[unit];
      }
      return undefined;
    };

    const filters = {
      extensions: options.extensions ? options.extensions.split(',').map(e => e.trim().toLowerCase()) : [],
      pattern: options.pattern,
      minSize: parseSize(options.minSize),
      maxSize: parseSize(options.maxSize),
      type: options.type === 'all' ? undefined : options.type,
      includeHidden: options.all,
    };

    try {
      const files = listFiles(dirPath, {
        recursive: options.recursive,
        maxDepth: parseInt(options.depth),
        filters,
        includeStats: options.stats,
        relativePath: options.relative,
      });

      if (options.json) {
        console.log(JSON.stringify(files, null, 2));
        return;
      }

      if (files.length === 0) {
        console.log(chalk.yellow('No files found matching the criteria.'));
        return;
      }

      console.log(chalk.cyan(`\n📂 Directory: ${dirPath}`));
      console.log(chalk.gray(`Found ${files.length} item(s)\n`));

      if (options.stats) {
        const headers = ['Name', 'Type', 'Size', 'Modified', 'Path'];
        const rows = files.map(file => [
          `${getFileIcon(file)} ${file.name}`,
          file.isDirectory ? 'DIR' : (file.isSymbolicLink ? 'LINK' : 'FILE'),
          file.formattedSize || '-',
          file.modified ? new Date(file.modified).toLocaleDateString() : '-',
          file.path,
        ]);
        console.log(formatTable(headers, rows));
      } else {
        files.forEach(file => {
          const icon = getFileIcon(file);
          const relativePath = options.relative ? file.path : path.relative(dirPath, file.fullPath);
          console.log(`${icon} ${chalk.gray(relativePath)}`);
        });
      }

      // Print summary
      const fileCount = files.filter(f => !f.isDirectory).length;
      const dirCount = files.filter(f => f.isDirectory).length;
      const totalSize = files.reduce((sum, f) => sum + (f.size || 0), 0);

      console.log(chalk.gray('\n─────────────────────────────────────'));
      console.log(chalk.cyan(`Summary: ${fileCount} files, ${dirCount} directories, ${formatFileSize(totalSize)} total`));

    } catch (error) {
      console.error(chalk.red(`✖ Error: ${error.message}`));
      process.exit(1);
    }
  });

// Tree command
program
  .command('tree [directory]')
  .description('Display directory tree structure')
  .option('-d, --depth <number>', 'Maximum depth to display', '5')
  .option('-e, --extensions <extensions>', 'Filter by file extensions')
  .option('-a, --all', 'Include hidden files')
  .option('--json', 'Output in JSON format')
  .action((directory = '.', options) => {
    console.log(banner);

    const dirPath = path.resolve(directory);

    if (!fs.existsSync(dirPath)) {
      console.error(chalk.red(`✖ Error: Directory not found: ${dirPath}`));
      process.exit(1);
    }

    const filters = {
      extensions: options.extensions ? options.extensions.split(',').map(e => e.trim().toLowerCase()) : [],
      includeHidden: options.all,
    };

    try {
      const tree = getDirectoryTree(dirPath, {
        maxDepth: parseInt(options.depth),
        filters,
      });

      if (options.json) {
        console.log(JSON.stringify(tree, null, 2));
        return;
      }

      // Print tree
      function printTree(node, prefix = '', isLast = true) {
        const connector = isLast ? '└── ' : '├── ';
        const icon = node.type === 'directory' ? chalk.blue('📁') : getFileIcon(node);

        console.log(`${prefix}${connector}${icon} ${node.name}`);

        if (node.children && node.children.length > 0) {
          const newPrefix = prefix + (isLast ? '    ' : '│   ');
          node.children.forEach((child, index) => {
            printTree(child, newPrefix, index === node.children.length - 1);
          });
        }
      }

      console.log(chalk.cyan(`\n📂 ${dirPath}\n`));
      printTree(tree);
      console.log();

    } catch (error) {
      console.error(chalk.red(`✖ Error: ${error.message}`));
      process.exit(1);
    }
  });

// Summary command
program
  .command('summary [directory]')
  .description('Display directory summary statistics')
  .option('-r, --recursive', 'Analyze recursively', 'true')
  .option('-e, --extensions <extensions>', 'Filter by file extensions')
  .option('--json', 'Output in JSON format')
  .action((directory = '.', options) => {
    console.log(banner);

    const dirPath = path.resolve(directory);

    if (!fs.existsSync(dirPath)) {
      console.error(chalk.red(`✖ Error: Directory not found: ${dirPath}`));
      process.exit(1);
    }

    const filters = {
      extensions: options.extensions ? options.extensions.split(',').map(e => e.trim().toLowerCase()) : [],
    };

    try {
      const summary = getDirectorySummary(dirPath, {
        recursive: options.recursive === 'true',
        filters,
      });

      if (options.json) {
        console.log(JSON.stringify(summary, null, 2));
        return;
      }

      console.log(chalk.cyan(`\n📊 Directory Summary: ${dirPath}\n`));

      console.log(chalk.bold('Overview:'));
      console.log(`  Total Items: ${chalk.white(summary.totalItems)}`);
      console.log(`  Files: ${chalk.white(summary.totalFiles)}`);
      console.log(`  Directories: ${chalk.white(summary.totalDirectories)}`);
      console.log(`  Total Size: ${chalk.white(summary.formattedTotalSize)}`);
      console.log(`  Average File Size: ${chalk.white(summary.formattedAverageFileSize)}\n`);

      if (summary.largestFile) {
        console.log(chalk.bold('Size Extremes:'));
        console.log(`  Largest: ${chalk.white(summary.largestFile.name)} (${formatFileSize(summary.largestFile.size)})`);
        console.log(`  Smallest: ${chalk.white(summary.smallestFile.name)} (${formatFileSize(summary.smallestFile.size)})\n`);
      }

      console.log(chalk.bold('File Size Distribution:'));
      console.log(`  Small (< 1MB): ${chalk.white(summary.filesBySize.small)}`);
      console.log(`  Medium (1-100MB): ${chalk.white(summary.filesBySize.medium)}`);
      console.log(`  Large (100MB-1GB): ${chalk.white(summary.filesBySize.large)}`);
      console.log(`  Extra Large (> 1GB): ${chalk.white(summary.filesBySize.xlarge)}\n`);

      if (summary.topExtensions.length > 0) {
        console.log(chalk.bold('Top File Extensions:'));
        summary.topExtensions.forEach(({ extension, count }) => {
          const percentage = ((count / summary.totalFiles) * 100).toFixed(1);
          console.log(`  .${chalk.cyan(extension.padEnd(5))} ${count} (${percentage}%)`);
        });
      }

      console.log();

    } catch (error) {
      console.error(chalk.red(`✖ Error: ${error.message}`));
      process.exit(1);
    }
  });

// Search command
program
  .command('search <pattern> [directory]')
  .description('Search for files by name pattern')
  .option('-r, --recursive', 'Search recursively', 'true')
  .option('-i, --case-sensitive', 'Case-sensitive search')
  .option('--json', 'Output in JSON format')
  .action((pattern, directory = '.', options) => {
    console.log(banner);

    const dirPath = path.resolve(directory);

    if (!fs.existsSync(dirPath)) {
      console.error(chalk.red(`✖ Error: Directory not found: ${dirPath}`));
      process.exit(1);
    }

    try {
      const results = searchFiles(dirPath, pattern, {
        recursive: options.recursive === 'true',
        caseSensitive: options.caseSensitive,
      });

      if (options.json) {
        console.log(JSON.stringify(results, null, 2));
        return;
      }

      console.log(chalk.cyan(`\n🔍 Search Results: "${pattern}" in ${dirPath}\n`));

      if (results.length === 0) {
        console.log(chalk.yellow('No matching files found.'));
        return;
      }

      console.log(chalk.gray(`Found ${results.length} match(es)\n`));

      results.forEach(file => {
        const relativePath = path.relative(dirPath, file.fullPath);
        console.log(`${getFileIcon(file)} ${chalk.gray(relativePath)}`);
      });

      console.log();

    } catch (error) {
      console.error(chalk.red(`✖ Error: ${error.message}`));
      process.exit(1);
    }
  });

// Duplicates command
program
  .command('duplicates [directory]')
  .description('Find duplicate files')
  .option('-r, --recursive', 'Search recursively', 'true')
  .option('--by-size', 'Group by size instead of name')
  .option('--json', 'Output in JSON format')
  .action((directory = '.', options) => {
    console.log(banner);

    const dirPath = path.resolve(directory);

    if (!fs.existsSync(dirPath)) {
      console.error(chalk.red(`✖ Error: Directory not found: ${dirPath}`));
      process.exit(1);
    }

    try {
      const duplicates = findDuplicates(dirPath, {
        recursive: options.recursive === 'true',
        byName: !options.bySize,
      });

      if (options.json) {
        console.log(JSON.stringify(duplicates, null, 2));
        return;
      }

      console.log(chalk.cyan(`\n👯 Duplicate Files: ${dirPath}\n`));

      if (duplicates.length === 0) {
        console.log(chalk.green('No duplicate files found.'));
        return;
      }

      console.log(chalk.gray(`Found ${duplicates.length} group(s) of duplicates\n`));

      duplicates.forEach((group, index) => {
        console.log(chalk.bold(`Group ${index + 1}:`));
        group.forEach(file => {
          const relativePath = path.relative(dirPath, file.fullPath);
          console.log(`  ${getFileIcon(file)} ${chalk.gray(relativePath)} ${chalk.white(`(${file.formattedSize})`)}`);
        });
        console.log();
      });

    } catch (error) {
      console.error(chalk.red(`✖ Error: ${error.message}`));
      process.exit(1);
    }
  });

// Default action - list files
program
  .argument('[directory]')
  .action((directory = '.') => {
    console.log(banner);
    const dirPath = path.resolve(directory);

    if (!fs.existsSync(dirPath)) {
      console.error(chalk.red(`✖ Error: Directory not found: ${dirPath}`));
      process.exit(1);
    }

    try {
      const files = listFiles(dirPath, { recursive: false });

      console.log(chalk.cyan(`\n📂 Directory: ${dirPath}\n`));

      if (files.length === 0) {
        console.log(chalk.yellow('Directory is empty.'));
        return;
      }

      // Separate directories and files
      const dirs = files.filter(f => f.isDirectory);
      const regularFiles = files.filter(f => !f.isDirectory);

      // Print directories first
      if (dirs.length > 0) {
        console.log(chalk.blue.bold('Directories:'));
        dirs.forEach(file => {
          console.log(`  ${getFileIcon(file)} ${chalk.blue(file.name)}`);
        });
        console.log();
      }

      // Print files
      if (regularFiles.length > 0) {
        console.log(chalk.white.bold('Files:'));
        regularFiles.forEach(file => {
          console.log(`  ${getFileIcon(file)} ${chalk.white(file.name)}`);
        });
      }

      console.log(chalk.gray(`\n${files.length} item(s) total\n`));

    } catch (error) {
      console.error(chalk.red(`✖ Error: ${error.message}`));
      process.exit(1);
    }
  });

// Parse arguments
program.parse(process.argv);
