//! Copies the installer's bundled demo-data resource into the data
//! directory (BRIEF v1.3 §6) so docker-compose.prod.yml's plain bind mount
//! (${VANTAGE_DATA_DIR}/demo-data:/data/demo:ro) has something to mount —
//! bind-mounting straight from the app bundle's own resource directory
//! would work on some OSes but not others (e.g. a read-only, checksum-
//! verified .app bundle on macOS), so this always normalizes to a plain
//! copy in the data dir first, same as postgres/minio/logs.

use std::fs;
use std::io;
use std::path::Path;

/// Idempotent: if the destination already has a manifest.json, assumes a
/// previous run already copied it and does nothing — demo data is static
/// (regenerated only by a maintainer re-running scripts/package/fetch_demo_data.py
/// and rebuilding the installer), never mutated at runtime.
pub fn ensure_demo_data(bundled_demo_data_dir: &Path, data_dir: &Path) -> io::Result<bool> {
    let dest = data_dir.join("demo-data");
    if dest.join("manifest.json").exists() {
        return Ok(false);
    }
    copy_dir_recursive(bundled_demo_data_dir, &dest)?;
    Ok(true)
}

fn copy_dir_recursive(src: &Path, dest: &Path) -> io::Result<()> {
    fs::create_dir_all(dest)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let dest_path = dest.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir_recursive(&entry.path(), &dest_path)?;
        } else {
            fs::copy(entry.path(), &dest_path)?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_fake_bundle(root: &Path) {
        fs::create_dir_all(root.join("2025-06-19")).unwrap();
        fs::write(root.join("manifest.json"), r#"{"items": []}"#).unwrap();
        fs::write(root.join("2025-06-19").join("visual.tif"), b"fake-tif-bytes").unwrap();
    }

    #[test]
    fn first_run_copies_everything_including_nested_scene_directories() {
        let src = tempfile::tempdir().unwrap();
        let data_dir = tempfile::tempdir().unwrap();
        make_fake_bundle(src.path());

        let copied = ensure_demo_data(src.path(), data_dir.path()).unwrap();
        assert!(copied);

        let dest = data_dir.path().join("demo-data");
        assert!(dest.join("manifest.json").is_file());
        assert!(dest.join("2025-06-19").join("visual.tif").is_file());
        assert_eq!(
            fs::read(dest.join("2025-06-19").join("visual.tif")).unwrap(),
            b"fake-tif-bytes"
        );
    }

    #[test]
    fn second_run_is_a_no_op_and_does_not_error_if_source_is_gone() {
        let src = tempfile::tempdir().unwrap();
        let data_dir = tempfile::tempdir().unwrap();
        make_fake_bundle(src.path());

        ensure_demo_data(src.path(), data_dir.path()).unwrap();

        // Simulate a second launch where the bundle resource path is (for
        // whatever reason) not passed a valid directory — should still be a
        // clean no-op because the destination already looks seeded.
        let missing_src = src.path().join("does-not-exist");
        let copied_again = ensure_demo_data(&missing_src, data_dir.path()).unwrap();
        assert!(!copied_again);
    }
}
