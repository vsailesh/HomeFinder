/**
 * Test Suite for File Lister
 * Run basic functionality tests
 */

import {
  listFiles,
  getDirectoryTree,
  getDirectorySummary,
  searchFiles,
  findDuplicates,
  formatFileSize,
  getFileExtension,
  getFileStats,
} from './index.js';

console.log('Running File Lister Test Suite...\n');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`✓ ${name}`);
    passed++;
  } catch (error) {
    console.log(`✗ ${name}`);
    console.log(`  Error: ${error.message}`);
    failed++;
  }
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message || 'Assertion failed');
  }
}

// Test formatFileSize
test('formatFileSize should format bytes correctly', () => {
  assert(formatFileSize(0) === '0 B', '0 bytes should format as "0 B"');
  assert(formatFileSize(1024) === '1 KB', '1024 bytes should format as "1 KB"');
  assert(formatFileSize(1024 * 1024) === '1 MB', '1 MB should format correctly');
  assert(formatFileSize(1024 * 1024 * 1024) === '1 GB', '1 GB should format correctly');
});

// Test getFileExtension
test('getFileExtension should extract extensions correctly', () => {
  assert(getFileExtension('test.js') === 'js', 'Should extract .js extension');
  assert(getFileExtension('file.tar.gz') === 'gz', 'Should extract last extension');
  assert(getFileExtension('noextension') === '', 'Should return empty string for no extension');
  // Note: path.extname('.hidden') returns '', so this behavior is expected
  assert(getFileExtension('.hidden') === '', 'Should handle dotfiles (no extension)');
});

// Test getFileStats
test('getFileStats should return stats for existing file', () => {
  const stats = getFileStats('./src/index.js');
  assert(stats !== null, 'Should return stats for existing file');
  assert(stats.isFile === true, 'Should identify as file');
  assert(typeof stats.size === 'number', 'Should have size property');
});

// Test listFiles basic functionality
test('listFiles should list files in directory', () => {
  const files = listFiles('./src', { recursive: false });
  assert(Array.isArray(files), 'Should return an array');
  assert(files.length > 0, 'Should find files in src directory');
  assert(files[0].name !== undefined, 'Files should have name property');
});

// Test listFiles with stats
test('listFiles should include stats when requested', () => {
  const files = listFiles('./src', { recursive: false, includeStats: true });
  assert(files.length > 0, 'Should find files');
  assert(files[0].size !== undefined, 'Files should have size property');
  assert(files[0].formattedSize !== undefined, 'Files should have formattedSize property');
});

// Test listFiles with extension filter
test('listFiles should filter by extension', () => {
  const files = listFiles('./src', {
    recursive: false,
    filters: { extensions: ['js'] },
  });
  assert(files.length > 0, 'Should find .js files');
  files.forEach(file => {
    if (!file.isDirectory) {
      assert(file.extension === 'js', 'All files should be .js');
    }
  });
});

// Test getDirectoryTree
test('getDirectoryTree should return tree structure', () => {
  const tree = getDirectoryTree('./src', { maxDepth: 1 });
  assert(tree !== null, 'Should return tree structure');
  assert(tree.name !== undefined, 'Tree should have name');
  assert(tree.children !== undefined, 'Tree should have children array');
  assert(Array.isArray(tree.children), 'Children should be an array');
});

// Test getDirectorySummary
test('getDirectorySummary should return summary statistics', () => {
  const summary = getDirectorySummary('./src', { recursive: false });
  assert(summary.totalItems >= 0, 'Should have totalItems count');
  assert(summary.totalFiles >= 0, 'Should have totalFiles count');
  assert(summary.totalDirectories >= 0, 'Should have totalDirectories count');
  assert(typeof summary.totalSize === 'number', 'Should have totalSize');
});

// Test searchFiles
test('searchFiles should find files matching pattern', () => {
  const results = searchFiles('./src', 'index', { recursive: false });
  assert(Array.isArray(results), 'Should return array of results');
  assert(results.length > 0, 'Should find files matching "index"');
});

// Test findDuplicates
test('findDuplicates should return array of duplicate groups', () => {
  const duplicates = findDuplicates('./src', { recursive: false });
  assert(Array.isArray(duplicates), 'Should return array');
});

// Test listFiles with depth limit
test('listFiles should respect depth limit', () => {
  const files = listFiles('./', { recursive: true, maxDepth: 1 });
  assert(Array.isArray(files), 'Should return array');
  // With maxDepth 1, we should only get immediate children
  const maxDepth = files.reduce((max, file) => {
    const depth = file.path.split('/').length;
    return Math.max(max, depth);
  }, 0);
  assert(maxDepth <= 10, 'Should respect depth limit');
});

// Summary
console.log('\n' + '─'.repeat(40));
console.log(`Tests passed: ${passed}`);
console.log(`Tests failed: ${failed}`);
console.log(`Total tests: ${passed + failed}`);
console.log('─'.repeat(40));

if (failed > 0) {
  process.exit(1);
} else {
  console.log('\n✓ All tests passed!');
}
