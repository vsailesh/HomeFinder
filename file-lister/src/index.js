/**
 * File Lister - Core Module
 * A comprehensive file system listing and analysis tool
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Get file statistics and information
 * @param {string} filePath - Path to the file
 * @returns {Object} File statistics
 */
export function getFileStats(filePath) {
  try {
    const stats = fs.statSync(filePath);
    return {
      size: stats.size,
      created: stats.birthtime,
      modified: stats.mtime,
      accessed: stats.atime,
      isDirectory: stats.isDirectory(),
      isFile: stats.isFile(),
      isSymbolicLink: stats.isSymbolicLink(),
      mode: stats.mode,
      permissions: stats.mode.toString(8).slice(-3),
    };
  } catch (error) {
    return null;
  }
}

/**
 * Convert file size to human-readable format
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted size string
 */
export function formatFileSize(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Get file extension
 * @param {string} filePath - Path to the file
 * @returns {string} File extension (without dot)
 */
export function getFileExtension(filePath) {
  const ext = path.extname(filePath);
  return ext.slice(1).toLowerCase();
}

/**
 * Check if a file matches the given filters
 * @param {string} fileName - Name of the file
 * @param {Object} stats - File statistics
 * @param {Object} filters - Filter criteria
 * @returns {boolean} True if file matches filters
 */
export function matchesFilters(fileName, stats, filters = {}) {
  // Extension filter
  if (filters.extensions && filters.extensions.length > 0) {
    const ext = getFileExtension(fileName);
    if (!filters.extensions.includes(ext)) {
      return false;
    }
  }

  // Pattern filter (regex)
  if (filters.pattern) {
    const regex = new RegExp(filters.pattern, 'i');
    if (!regex.test(fileName)) {
      return false;
    }
  }

  // Size filter
  if (filters.minSize !== undefined && stats.size < filters.minSize) {
    return false;
  }
  if (filters.maxSize !== undefined && stats.size > filters.maxSize) {
    return false;
  }

  // Type filter
  if (filters.type === 'files' && stats.isDirectory) {
    return false;
  }
  if (filters.type === 'directories' && !stats.isDirectory) {
    return false;
  }

  // Hidden files filter
  if (filters.includeHidden === false && fileName.startsWith('.')) {
    return false;
  }

  return true;
}

/**
 * List all files in a directory with optional recursive traversal
 * @param {string} dirPath - Path to the directory
 * @param {Object} options - Listing options
 * @returns {Array<Object>} Array of file information objects
 */
export function listFiles(dirPath, options = {}) {
  const {
    recursive = false,
    maxDepth = Infinity,
    currentDepth = 0,
    filters = {},
    includeStats = true,
    relativePath = false,
  } = options;

  const resolvedPath = path.resolve(dirPath);
  const results = [];

  if (currentDepth >= maxDepth) {
    return results;
  }

  let entries;
  try {
    entries = fs.readdirSync(resolvedPath, { withFileTypes: true });
  } catch (error) {
    throw new Error(`Cannot read directory: ${resolvedPath} - ${error.message}`);
  }

  for (const entry of entries) {
    const fullPath = path.join(resolvedPath, entry.name);
    const displayPath = relativePath
      ? path.relative(resolvedPath, fullPath)
      : fullPath;

    const stats = includeStats ? getFileStats(fullPath) : null;

    // Skip if stats couldn't be retrieved (e.g., permission denied)
    if (includeStats && !stats) {
      continue;
    }

    // Apply filters
    if (includeStats && !matchesFilters(entry.name, stats, filters)) {
      continue;
    }

    const fileInfo = {
      name: entry.name,
      path: displayPath,
      fullPath: fullPath,
      isDirectory: entry.isDirectory(),
      isSymbolicLink: entry.isSymbolicLink(),
    };

    if (includeStats && stats) {
      fileInfo.size = stats.size;
      fileInfo.formattedSize = formatFileSize(stats.size);
      fileInfo.created = stats.created;
      fileInfo.modified = stats.modified;
      fileInfo.permissions = stats.permissions;
      fileInfo.extension = entry.isDirectory() ? null : getFileExtension(entry.name);
    }

    results.push(fileInfo);

    // Recursively process subdirectories
    if (recursive && entry.isDirectory() && !entry.isSymbolicLink()) {
      const subOptions = {
        ...options,
        currentDepth: currentDepth + 1,
      };
      const subFiles = listFiles(fullPath, subOptions);
      results.push(...subFiles);
    }
  }

  return results;
}

/**
 * Get directory tree structure
 * @param {string} dirPath - Path to the directory
 * @param {Object} options - Tree options
 * @returns {Object} Tree structure
 */
export function getDirectoryTree(dirPath, options = {}) {
  const {
    maxDepth = Infinity,
    currentDepth = 0,
    filters = {},
  } = options;

  const resolvedPath = path.resolve(dirPath);

  if (currentDepth >= maxDepth) {
    return null;
  }

  let entries;
  try {
    entries = fs.readdirSync(resolvedPath, { withFileTypes: true });
  } catch (error) {
    return {
      name: path.basename(resolvedPath),
      path: resolvedPath,
      error: error.message,
      children: [],
    };
  }

  const node = {
    name: path.basename(resolvedPath) || resolvedPath,
    path: resolvedPath,
    type: 'directory',
    children: [],
  };

  // Sort entries: directories first, then files
  entries.sort((a, b) => {
    if (a.isDirectory() && !b.isDirectory()) return -1;
    if (!a.isDirectory() && b.isDirectory()) return 1;
    return a.name.localeCompare(b.name);
  });

  for (const entry of entries) {
    const fullPath = path.join(resolvedPath, entry.name);
    const stats = getFileStats(fullPath);

    // Skip if stats couldn't be retrieved
    if (!stats) {
      continue;
    }

    // Apply filters
    if (!matchesFilters(entry.name, stats, filters)) {
      continue;
    }

    if (entry.isDirectory() && !entry.isSymbolicLink()) {
      const childNode = getDirectoryTree(fullPath, {
        ...options,
        currentDepth: currentDepth + 1,
      });
      if (childNode) {
        node.children.push(childNode);
      }
    } else {
      node.children.push({
        name: entry.name,
        path: fullPath,
        type: entry.isSymbolicLink() ? 'symlink' : 'file',
        extension: getFileExtension(entry.name),
        size: stats.size,
        formattedSize: formatFileSize(stats.size),
      });
    }
  }

  return node;
}

/**
 * Get directory summary statistics
 * @param {string} dirPath - Path to the directory
 * @param {Object} options - Summary options
 * @returns {Object} Summary statistics
 */
export function getDirectorySummary(dirPath, options = {}) {
  const {
    recursive = true,
    filters = {},
  } = options;

  const files = listFiles(dirPath, { recursive, filters, includeStats: true });

  const summary = {
    totalItems: files.length,
    totalFiles: 0,
    totalDirectories: 0,
    totalSize: 0,
    largestFile: null,
    smallestFile: null,
    fileExtensions: {},
    filesBySize: {
      small: 0,    // < 1MB
      medium: 0,   // 1MB - 100MB
      large: 0,    // 100MB - 1GB
      xlarge: 0,   // > 1GB
    },
  };

  for (const file of files) {
    if (file.isDirectory) {
      summary.totalDirectories++;
    } else {
      summary.totalFiles++;
      summary.totalSize += file.size || 0;

      // Track largest and smallest files
      if (!file.isDirectory && file.size !== undefined) {
        if (!summary.largestFile || file.size > summary.largestFile.size) {
          summary.largestFile = { name: file.name, size: file.size, path: file.path };
        }
        if (!summary.smallestFile || file.size < summary.smallestFile.size) {
          summary.smallestFile = { name: file.name, size: file.size, path: file.path };
        }

        // Categorize by size
        if (file.size < 1024 * 1024) {
          summary.filesBySize.small++;
        } else if (file.size < 100 * 1024 * 1024) {
          summary.filesBySize.medium++;
        } else if (file.size < 1024 * 1024 * 1024) {
          summary.filesBySize.large++;
        } else {
          summary.filesBySize.xlarge++;
        }
      }

      // Track file extensions
      if (file.extension) {
        summary.fileExtensions[file.extension] = (summary.fileExtensions[file.extension] || 0) + 1;
      }
    }
  }

  summary.formattedTotalSize = formatFileSize(summary.totalSize);
  summary.averageFileSize = summary.totalFiles > 0 ? summary.totalSize / summary.totalFiles : 0;
  summary.formattedAverageFileSize = formatFileSize(summary.averageFileSize);

  // Sort extensions by count
  summary.topExtensions = Object.entries(summary.fileExtensions)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([ext, count]) => ({ extension: ext, count }));

  return summary;
}

/**
 * Search for files by name pattern
 * @param {string} dirPath - Root directory to search
 * @param {string} pattern - Search pattern (regex)
 * @param {Object} options - Search options
 * @returns {Array<Object>} Matching files
 */
export function searchFiles(dirPath, pattern, options = {}) {
  const { recursive = true, caseSensitive = false } = options;

  const files = listFiles(dirPath, {
    recursive,
    includeStats: true,
    includeHidden: true,
  });

  const regex = new RegExp(pattern, caseSensitive ? '' : 'i');

  return files.filter(file => regex.test(file.name));
}

/**
 * Find duplicate files by size and name
 * @param {string} dirPath - Directory to search
 * @param {Object} options - Search options
 * @returns {Array<Array<Object>>} Groups of duplicate files
 */
export function findDuplicates(dirPath, options = {}) {
  const { recursive = true, byName = true } = options;

  const files = listFiles(dirPath, {
    recursive,
    includeStats: true,
    filters: { type: 'files' },
  });

  const groups = {};

  for (const file of files) {
    if (file.isDirectory) continue;

    let key;
    if (byName) {
      key = file.name.toLowerCase();
    } else {
      // Group by size (rounded to nearest KB for approximate matching)
      key = Math.round((file.size || 0) / 1024);
    }

    if (!groups[key]) {
      groups[key] = [];
    }
    groups[key].push(file);
  }

  // Return only groups with duplicates
  return Object.values(groups).filter(group => group.length > 1);
}

export default {
  getFileStats,
  formatFileSize,
  getFileExtension,
  matchesFilters,
  listFiles,
  getDirectoryTree,
  getDirectorySummary,
  searchFiles,
  findDuplicates,
};
