# TRACE AI X — Google Play Data Safety worksheet

This worksheet must match the production binary and backend behavior. Copy the final answers into Play Console before rollout.

## Data collected
| Google Play category | TRACE AI X data | Collected? | Required/Optional | Purpose |
|---|---|---:|---|---|
| Personal info → User IDs | Pi UID / Pi username | Yes | Required for Pi-auth users | Account management, authentication, security |
| Location → Precise location | GPS coordinates when user invokes location features | Yes | Optional / user-initiated | App functionality, geofence/map features |
| Location → Approximate location | May be available through coarse permission | Yes | Optional / user-initiated | App functionality |
| Photos and videos → Photos | Camera/evidence uploads | Yes | Optional / user-initiated | App functionality |
| Photos and videos → Videos | Evidence uploads | Yes | Optional / user-initiated | App functionality |
| User-generated content → Other user-generated content | Case notes, timeline descriptions, evidence notes | Yes | Depends on feature use | App functionality |
| App activity → App interactions | Security/audit events for sensitive operations | Yes | Required for protected operations | Security, fraud prevention, app functionality |

## Data NOT collected by current Android release
- Contacts
- SMS/MMS
- Call log
- Microphone/audio recording
- Background location
- Pi wallet passphrase
- Installed-app inventory
- Advertising ID for advertising

## Sharing
Do not mark data as shared unless the production system actually transfers user data to an external third party for that party's own purposes. Service providers/processors must be evaluated using Google Play's Data Safety definitions.

## Security practices
- Data in transit: HTTPS.
- Role-based access control.
- Short-lived authenticated sessions.
- Audit log for sensitive operations.
- Account deletion in app.
- External deletion request page: https://tracevnid.fyi/delete-account.html

## Account deletion
- In-app: authenticated "Xóa tài khoản" action.
- External: /delete-account.html → /public/account-deletion-request.
- Ownership is verified before an external request is executed.
- User account and evidence uploaded by that account are deleted.
- Legally/operationally retained records are de-identified from the Pi UID.

## Play Console checklist
- Complete Data safety.
- Enter https://tracevnid.fyi/delete-account.html as the account-deletion web resource.
- App access: provide the dedicated Google Play reviewer credentials.
- Location: state that precise/coarse location is user-initiated and no background location is requested.
- Photos/videos: state that capture/upload occurs only after explicit user action.
