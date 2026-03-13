# Epic 1: Identity & Access Management (IAM)

**Branch**: `1-epic-1-iam`
**Status**: Draft
**Created**: 2026-03-12

---

## Overview

Marketing teams operate within a shared platform where different members have different levels of responsibility. This epic establishes the foundational access layer: who can enter the platform, what they are allowed to do once inside, and how their access is cleanly terminated when no longer needed.

Without this foundation, no other part of the platform can be safely built. Every subsequent feature depends on knowing *who* is acting and *whether* they are permitted to act.

---

## Goals

1. Allow the designated administrator to establish the organization's presence on the platform through a secure, protected registration process.
2. Ensure that every user on the platform operates under a clearly defined role that determines what they can see and do.
3. Provide administrators with the tools to grow their team through invitation, adjust responsibilities through role changes, and remove access cleanly through revocation.
4. Guarantee that a user's session is reliably terminated upon logout, leaving no residual access.

---

## User Scenarios & Testing

### Scenario 1: First-Time Admin Registration

**Actor**: Designated administrator
**Precondition**: The administrator has been issued a valid registration credential by the platform operator.

1. The administrator accesses the registration endpoint using their credential.
2. They provide their name, email address, and a chosen password.
3. The system creates their account, establishes them as the Admin, and confirms success.
4. The administrator is able to log in immediately after registration.

**Acceptance**: Registration succeeds only when a valid platform-issued credential is presented. Attempted registration without it is rejected with an explanatory message.

---

### Scenario 2: Admin Logs In

**Actor**: Admin (or any user with an active account)
**Precondition**: The user has a registered account.

1. The user provides their email and password.
2. The system validates their credentials and establishes a session.
3. The user is granted access appropriate to their role.
4. The session persists across page loads without requiring re-entry of credentials.

**Acceptance**: Incorrect credentials are rejected. A session is created only for valid, active accounts. Accounts that have been deactivated cannot log in.

---

### Scenario 3: Admin Invites a New Team Member

**Actor**: Admin
**Precondition**: Admin is logged in.

1. Admin provides the new team member's email address and selects a role (Marketing Manager or Marketer).
2. The system generates a time-limited invitation and delivers it to the provided email address.
3. The invitee receives the invitation and follows the link to complete their registration (name, password).
4. The invitee's account is created with the assigned role and they can log in immediately.

**Acceptance**:
- Invitation links expire after 72 hours. Expired links are rejected with a clear message prompting the admin to re-send.
- An invitation cannot be used more than once.
- Only Admins can issue invitations. A Marketing Manager or Marketer attempting to invite receives a permission error.

---

### Scenario 4: Marketing Manager Invites a Marketer

**Actor**: Marketing Manager
**Precondition**: Marketing Manager is logged in.

1. Marketing Manager attempts to invite a new user.
2. The system rejects the action and returns a permission error.

**Acceptance**: Marketing Managers cannot invite users of any role. This action is reserved for Admins only.

> **Note**: This scenario is included explicitly to confirm the boundary. If the intended behavior is that Marketing Managers *can* invite Marketers, this scenario and Scenario 3's acceptance criteria must be updated. See Assumptions.

---

### Scenario 5: Admin Changes a User's Role

**Actor**: Admin
**Precondition**: Admin is logged in. Target user has an existing account.

1. Admin selects a team member and chooses a new role for them.
2. The system updates the user's role.
3. On the user's next action (or immediately if active), their permissions reflect the new role.

**Acceptance**:
- A user's role cannot be changed to a role that does not exist in the system.
- An Admin cannot demote themselves. An attempt returns a clear error.
- The role change is logged with the acting Admin's identity and a timestamp.

---

### Scenario 6: User Logs Out

**Actor**: Any authenticated user
**Precondition**: User has an active session.

1. User initiates logout.
2. The system terminates the session immediately.
3. Any subsequent attempt to use the previous session is rejected.

**Acceptance**: After logout, the user's prior session token or credential is no longer accepted by any endpoint. No residual access persists.

---

### Scenario 7: Admin Revokes a User's Access

**Actor**: Admin
**Precondition**: Admin is logged in. Target user has an active account.

1. Admin selects a team member and revokes their access.
2. The system deactivates the account.
3. Any active sessions for that user are immediately invalidated.
4. The user cannot log in again after revocation.

**Acceptance**: Revocation takes effect immediately — not at session expiry. The revoked user's next request to any protected endpoint is rejected. Reactivation of a revoked account requires an Admin's explicit action.

---

## Functional Requirements

### FR-1: Admin Registration

| ID | Requirement |
|----|-------------|
| FR-1.1 | A new Admin can only register by presenting a valid, platform-issued registration credential. |
| FR-1.2 | Registration requires a unique email address, a display name, and a password meeting complexity requirements. |
| FR-1.3 | Registering with an email address already in use returns a clear error. |
| FR-1.4 | A newly registered Admin is granted the Admin role and becomes the first user in the system. |

---

### FR-2: Authentication & Sessions

| ID | Requirement |
|----|-------------|
| FR-2.1 | Users authenticate using their email address and password. |
| FR-2.2 | Successful authentication creates a session that remains valid across page loads without re-entry of credentials. |
| FR-2.3 | Sessions expire automatically after a period of inactivity (default: 8 hours). |
| FR-2.4 | Deactivated accounts cannot authenticate. |
| FR-2.5 | After 5 consecutive failed login attempts, the account is temporarily locked for 15 minutes. The user is informed of the lockout. |
| FR-2.6 | Passwords are never stored or transmitted in plaintext. |

---

### FR-3: Role-Based Access Control

| ID | Requirement |
|----|-------------|
| FR-3.1 | Every user is assigned exactly one role: Admin, Marketing Manager, or Marketer. |
| FR-3.2 | Role permissions are enforced on every protected action. A user without the required role receives a clear, non-revealing error. |
| FR-3.3 | The permission model for each role is defined as follows: |

**Role Permission Matrix**

| Capability | Admin | Marketing Manager | Marketer |
|---|:---:|:---:|:---:|
| Initial system setup | Yes | No | No |
| Invite users (any role) | Yes | No | No |
| Change any user's role | Yes | No | No |
| Revoke any user's access | Yes | No | No |
| View all team members | Yes | Yes | No |
| Manage content | Yes | Yes | Yes |
| View own profile | Yes | Yes | Yes |

---

### FR-4: User Invitations

| ID | Requirement |
|----|-------------|
| FR-4.1 | Admins can invite a new user by providing an email address and a target role. |
| FR-4.2 | The system sends an invitation to the provided email address containing a unique, single-use link. |
| FR-4.3 | Invitation links are valid for 72 hours from the time of issue. |
| FR-4.4 | An invitation link that has expired or already been used returns a clear error and prompts the user to request a new invitation. |
| FR-4.5 | An Admin can resend an invitation to an email address with a pending (unused, unexpired) invitation, which invalidates the prior invitation and issues a new one. |
| FR-4.6 | Inviting an email address that already has an active account returns a clear error. |
| FR-4.7 | The invitee sets their display name and password when accepting the invitation. The assigned role is fixed at time of invitation and cannot be changed during acceptance. |

---

### FR-5: Role Management

| ID | Requirement |
|----|-------------|
| FR-5.1 | Admins can change any team member's role to any valid role except their own. |
| FR-5.2 | An Admin cannot change their own role. |
| FR-5.3 | Every role change is recorded with the Admin's identity, the affected user's identity, the old role, the new role, and the timestamp. |
| FR-5.4 | A role change takes effect on the user's next authenticated action. |

---

### FR-6: Session Revocation & Logout

| ID | Requirement |
|----|-------------|
| FR-6.1 | Any user can log out, which immediately terminates their current session. |
| FR-6.2 | After logout, the terminated session is no longer accepted on any endpoint. |
| FR-6.3 | Admins can revoke access for any team member, which immediately deactivates their account and terminates all active sessions. |
| FR-6.4 | A deactivated user's next request to any protected endpoint is rejected, regardless of whether their session token has not yet expired. |

---

## Success Criteria

| # | Criterion |
|---|-----------|
| SC-1 | A new Admin can complete registration and gain access to the platform in under 2 minutes. |
| SC-2 | An invited user can accept an invitation and reach their first logged-in screen in under 3 minutes. |
| SC-3 | A revoked user's access is terminated within 5 seconds of an Admin completing the revocation action. |
| SC-4 | Zero instances of a lower-privilege role successfully performing an action reserved for a higher-privilege role, as measured across automated permission boundary tests. |
| SC-5 | After logout, 100% of subsequent requests using the prior session are rejected. |
| SC-6 | Account lockout activates within the same request that triggers the 5th consecutive failed login attempt. |
| SC-7 | All authentication and authorization events (login, logout, invitation, role change, revocation) are captured in the audit log with no gaps. |

---

## Key Entities

### User
Represents a registered individual on the platform.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| email | Unique login identifier. Never exposed in logs. |
| display_name | User's name as shown in the UI |
| password_hash | Stored credential. Never plaintext. |
| role | One of: Admin, Marketing Manager, Marketer |
| status | Active or Deactivated |
| created_at | Account creation timestamp |
| deactivated_at | Timestamp of revocation (nullable) |

---

### Role
A named set of permissions. Fixed set for MVP: Admin, Marketing Manager, Marketer.

---

### Invitation
A time-limited, single-use credential for a new user to join the platform.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| invited_email | Email address the invitation was sent to |
| assigned_role | Role the new user will receive on acceptance |
| issued_by | Admin who created the invitation |
| issued_at | Timestamp of creation |
| expires_at | 72 hours after `issued_at` |
| status | Pending, Accepted, or Expired |

---

### Session
A record of an active authenticated user session.

| Attribute | Description |
|-----------|-------------|
| id | Unique session identifier |
| user_id | The authenticated user |
| created_at | Session start time |
| last_active_at | Most recent activity timestamp |
| expires_at | Calculated expiry (8 hours from last activity) |
| revoked | Boolean — true if explicitly terminated |

---

### Audit Log Entry
An immutable record of any security-relevant action.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| action | Event type (login, logout, invite_sent, role_changed, access_revoked, etc.) |
| actor_id | User who performed the action |
| target_id | User affected (nullable for non-user actions) |
| metadata | JSON blob of before/after values (e.g., old_role, new_role) |
| timestamp | When the event occurred |

---

## Dependencies & Assumptions

### Dependencies
- **Email delivery**: The invitation flow depends on a transactional email service being available. Email delivery failure handling is out of scope for this epic (see Out of Scope).
- **Platform-issued registration credential**: Admin registration requires a credential issued externally. The mechanism for generating and distributing this credential is out of scope for this epic.

### Assumptions

| # | Assumption | Rationale |
|---|-----------|-----------|
| A-1 | Only Admins can invite users. Marketing Managers cannot invite anyone. | Preserves tight control over team membership. Can be revisited post-MVP. |
| A-2 | The platform has exactly three roles in MVP: Admin, Marketing Manager, Marketer. Custom roles are out of scope. | Simplifies permission enforcement and avoids premature role engine complexity. |
| A-3 | Session inactivity timeout is 8 hours. | Standard default for business applications; can be made configurable later. |
| A-4 | An Admin cannot demote themselves. | Prevents accidental loss of administrative access to the system. |
| A-5 | The system must have at least one Admin at all times. Revoking the last Admin is blocked. | Prevents the installation from becoming inaccessible. |
| A-6 | Invitation expiry is 72 hours. | Balances convenience (enough time to act) with security (not indefinitely open). |
| A-7 | Passwords must be at minimum 10 characters and include at least one uppercase letter, one number, and one special character. | Industry-standard baseline; exact rules can be tightened. |

---

## Out of Scope

- Social login / OAuth2 sign-in (Google, GitHub, etc.)
- Multi-factor authentication (MFA) — planned for a future epic
- Self-service password reset (planned for a future epic)
- Email delivery failure handling and retry logic
- Custom or configurable roles beyond the three defined here
- Admin self-registration without a platform-issued credential
- Audit log querying UI — the log is written in this epic; retrieval UI is a future epic
- The mechanism by which the initial Admin registration credential is generated and distributed to the installing organization
