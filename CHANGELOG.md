# Changelog

## [2.0] - 2026-07-10

### Added
- Automatic detection of upstream and downstream nodes.
- Automatic retrieval of street and municipality names.
- Updated the plugin configuration:
    - Support the French National Address Database (BAN) layer.
    - Add NF EN 13508-2 field :
        - material
        - diameter
        - shape
        - effluent 

###Fixed
- Fixed incorrect field labels for the #B01 and #B03 tags.
- Fixed orientation AAK

## [1.1] - 2026-07-09

### Added
- Added support for the `#A3` and `#A5` tags according to the standard specification.

### Fixed
- Fixed the processing of the last block when it does not contain a `#Z` tag.