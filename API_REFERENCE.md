# AgroTrack API Reference & Developer Guide

Welcome to the AgroTrack API. This guide explains how everything works together — from the moment a sender registers an account, to the final proof of delivery.

**Base URL (local):** `http://localhost:8000/api/v1`  
**Base URL (production):** `https://<your-app>.up.railway.app/api/v1`

Interactive API Docs: [Swagger UI](/api/docs/swagger/) | [ReDoc](/api/docs/)

---

## 1. Authentication & Users

Before anyone can use the protected API, they need an account and a JWT.

### Registering and Verifying
1. **`POST /auth/register/`**: Create a new account. The system will email a 6-digit OTP to the user.
2. **`POST /auth/verify-otp/`**: Validate the OTP. Returns a **JWT Access Token** (15 minutes) and a **Refresh Token** (7 days).

### Logging In
1. **`POST /auth/login/`**: Exchange an email and password for a JWT pair.
2. **`POST /auth/token/refresh/`**: Send your refresh token to get a fresh access token.
3. **`POST /auth/logout/`**: Blacklist your refresh token and end the session.

All protected endpoints require the access token in the header:
`Authorization: Bearer <access_token>`

---

## 2. Order Creation (The Sender)

When a sender wants to ship agricultural commodities, they create a new Order.

### Create a Shipment
**`POST /orders/`** *(Requires `sender` role)*

Senders provide the pickup address, delivery address, cargo details, and contacts.
```json
{
  "pickup_address": "Farm 4, Ota, Ogun State",
  "pickup_contact_name": "Farmer Joe",
  "pickup_phone": "08033333333",
  "delivery_address": "Mile 12 Market, Lagos",
  "delivery_name": "Mama Tomato",
  "delivery_phone": "08044444444",
  "cargo_type": "Fresh Tomatoes",
  "cargo_weight": 500.00,
  "cargo_value": 200000.00,
  "cargo_priority": "standard",
  "pickup_date": "2026-07-03"
}
```
**What happens:**
- The system generates an 8-character tracking number (e.g., `AGT30459921`).
- The order status is `new_request`.
- The Timeline automatically logs an **"Order Placed"** event.

---

## 3. Dispatch & Fleet Assignment (The Dispatcher)

A dispatcher logs in to see the global queue of unassigned shipments.

### Viewing the Queue & Fleet
- **`GET /orders/`**: Lists all orders. Filtering by `?status=new_request` shows unassigned trips.
- **`GET /orders/drivers/`**: Lists available drivers to take the trip.
- **`GET /orders/vehicles/`**: Lists available trucks/vans to carry the cargo.

### Claiming and Assigning the Order
**`PATCH /orders/{id}/`** *(Requires `dispatcher` or `admin` role)*

The dispatcher claims the order and assigns resources:
```json
{
  "dispatcher": 15,
  "driver": 4,
  "vehicle": 12,
  "status": "assigned",
  "total_cost": 45000.00
}
```
**What happens:**
- The order is now locked to this dispatcher.
- The Timeline automatically logs **"Dispatcher Assigned"** and **"Driver & Vehicle Assigned"**.

> **Double-booking protection:** If the selected driver or vehicle is currently assigned to another active (non-completed, non-cancelled) trip, the API returns a `400 Bad Request` with a clear error on the `driver_id` or `vehicle_id` field. Free up your resources first.

---

## 4. Transit & Live Tracking

Once the truck leaves the farm, the dispatcher tracks it through the system.

### Updating Status & Location
**`PATCH /orders/{id}/`**

As the journey progresses, the dispatcher updates the location and status:
1. `{"status": "pending_pickup"}` → Timeline logs **"Pickup Confirmed"**.
2. `{"status": "in_transit", "current_location": "Leaving Ota"}` → Timeline logs **"In Transit"** and the checklist advances.
3. `{"current_location": "Approaching Lagos"}` → Timeline logs an additional **"Location Update"** breadcrumb. The step checklist stays at "In Transit" but the description updates to the latest location.
4. `{"status": "delivered"}` → Timeline logs **"Delivered"**.

### Viewing the Journey Tracker
**`GET /orders/{id}/timeline/`**

Returns the timeline in two distinct structures for the UI:
1. **`checklist`**: A fixed 6-step progress indicator. Each step has a `state` property.
2. **`events`**: The raw, chronological log of all events, including every single location update breadcrumb.

#### Checklist Step States

| `state` | Meaning | Suggested UI |
|---|---|---|
| `"completed"` | Step is fully done | ✅ Green checkmark icon |
| `"current"` | Step is actively in progress | 🔄 Spinning / active icon |
| `"pending"` | Step not yet reached | ⬜ Greyed-out circle |

The 6 fixed steps in order: `order_placed` → `assigned` → `pending_pickup` → `in_transit` → `delivered` → `completed`.

**Example Response:**
```json
{
  "success": true,
  "message": "Timeline retrieved.",
  "data": {
    "checklist": [
      {
        "step": "order_placed",
        "label": "Order Placed",
        "state": "completed",
        "description": "Order was placed by Sender",
        "timestamp": "2026-07-08T09:15:00Z",
        "event_id": 142
      },
      {
        "step": "in_transit",
        "label": "In Transit",
        "state": "current",
        "description": "Approaching Lokoja, Kogi State",
        "timestamp": null,
        "event_id": null
      },
      {
        "step": "delivered",
        "label": "Delivered",
        "state": "pending",
        "description": null,
        "timestamp": null,
        "event_id": null
      }
    ],
    "events": [
      {
        "id": 154,
        "title": "Location Update",
        "description": "Approaching Lokoja, Kogi State",
        "timestamp": "2026-07-08T16:30:00Z"
      },
      {
        "id": 150,
        "title": "In Transit",
        "description": "Truck left the farm en route to destination.",
        "timestamp": "2026-07-08T11:30:00Z"
      }
    ]
  }
}
```

> **UI Tip:** Map over `data.checklist` to render the 6-step progress bar (switch on `item.state` for icons). Map over `data.events` for the scrollable breadcrumb history beneath it.

### Editing Timeline History
**`PATCH /orders/timeline/{event_id}/`** *(Requires `dispatcher` or `admin` role)*

If a dispatcher makes a typo in a location update, they can edit the description retroactively using the `event_id` returned in the timeline.
```json
{
  "description": "Approaching Lokoja, Kogi State"
}
```

### Public Tracking
**`GET /public/track/{tracking_number}/`** *(No Auth Required)*

Anyone with the `AGT...` tracking number can hit this endpoint to get the live location, ETA, and the full history of the trip. No login required.

---

## 5. Context-Aware Chat System

During the journey, the Sender and the assigned Dispatcher can message each other directly.

### Order-Scoped Thread
**`GET /orders/{id}/messages/`**

Returns the chat history for a single order, the unread count, and `chat_info` identifying the other party (with initials for UI avatars). Access is strictly limited to the sender and the assigned dispatcher.

**`POST /orders/{id}/messages/`**
```json
{
  "content": "Is the truck delayed by the rain?"
}
```

**`POST /orders/{id}/messages/read/`**

When the user opens the chat UI, call this endpoint. It bulk-updates all incoming messages from the other party to `is_read = true`, clearing the unread badge.

### Dispatcher Inbox (All Orders)
**`GET /orders/messages/`** *(Requires `dispatcher` or `admin` role)*

Returns every message across **all** orders assigned to the requesting dispatcher in a flat, newest-first list — perfect for a notification inbox panel.

**Response:**
```json
{
  "success": true,
  "message": "Dispatcher inbox retrieved.",
  "data": {
    "total_count": 12,
    "unread_count": 3,
    "messages": [
      {
        "id": 42,
        "order_id": 18,
        "tracking_number": "AGT12345678",
        "pickup_address": "Farm A, Kano",
        "delivery_address": "Mile 12, Lagos",
        "sender_id": 5,
        "sender_name": "Emeka Okafor",
        "sender_initials": "E",
        "is_own_message": false,
        "content": "Is the truck at the farm yet?",
        "is_read": false,
        "timestamp": "2026-07-20T08:45:00Z"
      }
    ]
  }
}
```

> `unread_count` only counts messages from senders — not the dispatcher's own sent messages.
> `is_own_message` drives left/right bubble placement in a chat-style inbox UI.
> Each message carries `tracking_number` + addresses so the frontend can link directly to the order without an extra API call.

### Dispatcher Unread — Grouped by Chat
**`GET /orders/messages/unread/`** *(Requires `dispatcher` or `admin` role)*

Returns **only unread messages**, grouped by order/chat thread. Use this to show per-chat badge counts in the dispatcher UI.

**Response:**
```json
{
  "success": true,
  "message": "3 unread messages across 2 chats.",
  "data": {
    "total_unread": 3,
    "threads": [
      {
        "order_id": 18,
        "tracking_number": "AGT12345678",
        "pickup_address": "Farm A, Kano",
        "delivery_address": "Mile 12, Lagos",
        "unread_count": 2,
        "messages": [
          {
            "id": 42,
            "sender_name": "Emeka Okafor",
            "sender_initials": "E",
            "content": "Is the truck at the farm yet?",
            "timestamp": "2026-07-20T08:45:00Z"
          }
        ]
      }
    ]
  }
}
```

> **Typical frontend flow:**
> 1. Poll `GET /orders/messages/unread/` on page load → render badge counts per thread.
> 2. User opens a chat → call `POST /orders/{id}/messages/read/` to clear that chat only.
> 3. Re-fetch unread → the opened chat disappears from threads; others remain intact.

---

## 6. Ratings & Reviews

Once a shipment is complete, the sender can leave a 1–5 star rating and comment for their driver.

### Submit a Rating
**`POST /orders/{id}/rate/`** *(Requires `sender` role)*

```json
{
  "rating": 5,
  "comment": "Smooth delivery, arrived early!"
}
```

**Validation rules:**
- `rating` must be an integer between 1 and 5.
- The order must have `status = completed`.
- The order must have a driver assigned.
- Each order can only be rated once — attempting again returns `400`.
- Only the order's own sender can rate it — others get `404`.

**What happens after a successful submission:**
- A `Review` record is saved against the order.
- The assigned driver's average `rating` is recalculated and saved immediately.
- The platform-wide `customer_rating` in `GET /public/stats/` updates automatically.

### Where ratings surface

| Endpoint | Field | Scope |
|---|---|---|
| `GET /orders/` | `data[].review` | **Per-order** rating embedded on each order in the list |
| `GET /orders/{id}/` | `data.review` | **Per-order** rating embedded on the order detail |
| `GET /orders/drivers/` | `rating` | Per-driver aggregate average (for dispatcher assignment view) |
| `GET /admin/drivers/` | `rating` | Per-driver aggregate average (for admin oversight) |
| `GET /admin/drivers/{id}/` | `rating` | Full driver detail with aggregate rating |
| `GET /public/stats/` | `data.customer_rating` | Platform-wide average across all reviews (e.g. `"4.8 / 5"`) |

### Order response with embedded review

Every order — in both the list and detail endpoints — now carries its own `review` field:

```json
{
  "success": true,
  "message": "Shipment details retrieved.",
  "data": {
    "id": 18,
    "tracking_number": "AGT12345678",
    "status": "completed",
    "driver": {
      "id": 4,
      "name": "Bola Ahmed",
      "rating": 4.2
    },
    "review": {
      "id": 3,
      "rating": 5,
      "comment": "Great driver, arrived early!",
      "timestamp": "2026-07-22T10:30:00Z"
    }
  }
}
```

> If the order has not been rated yet, `review` is `null`. Use this to conditionally render a **"Leave a Review"** CTA vs. displaying the submitted rating in your UI.

---

## 7. Proof of Delivery (Completion)

When the goods arrive and are signed for, the dispatcher uploads the signed waybill to close out the order.

### Uploading the POD
**`POST /orders/{id}/pod/`** *(Requires `dispatcher` or `admin` role, sent as `multipart/form-data`)*

Uploads the proof of delivery image and automatically advances the order status to `completed`.

**Validation Rules:**
- The order must currently be in `delivered` status.
- The user must be the dispatcher assigned to this specific order (admins are exempt).
- The image must be a valid format (JPEG, PNG, WEBP) and under 10 MB.

**Form Data:**
| Field | Type | Description |
|---|---|---|
| `proof_of_delivery` | File | The image file (max 10MB) |

**Success Response (`200 OK`):**
```json
{
  "success": true,
  "message": "Proof of delivery uploaded successfully. Order is now completed.",
  "data": {
    "order_id": 18,
    "tracking_number": "AGT12345678",
    "status": "completed",
    "proof_of_delivery": "http://localhost:8000/media/pod/waybill_18.jpg"
  }
}
```
- The Timeline logs the final **"Completed"** event.
- The order drops off the active queue.

---

## 7. Dashboards & Analytics

Both the Operations and Admin teams have dedicated dashboards to monitor the business.

### Operations Dashboard
**`GET /orders/dashboard/`**
Returns high-level counts: Active Orders, Pending Deliveries, Total Delivered, and Revenue (for dispatchers/admins).

### Admin Portal
The `/admin/` endpoints are restricted strictly to users with `role = admin`.

- **Platform Setup**: Register new fleet vehicles (`POST /admin/vehicles/`) and drivers (`POST /admin/drivers/`).
- **User Management**: View or suspend sender accounts (`PATCH /admin/users/{id}/`).
- **Global Settings**: Configure platform-wide pricing and notification rules via the singleton settings `GET|PATCH /admin/settings/`.
- **Deep Analytics**: Fetch revenue graphs, regional distribution, and user acquisition metrics (`GET /admin/analytics/`).

> **Note on Driver Updates:** Use `PATCH /admin/drivers/{id}/` only — `PUT` is intentionally blocked to prevent accidentally nulling out fields. Only send the fields you want to change.

---

## 8. Cost Estimation (No Auth Required)

**`POST /public/estimate/`**

Calculates a shipping cost estimate from two plain-text addresses. No coordinates or distance knowledge needed from the frontend.

### How It Works
1. Both addresses are geocoded via **Nominatim** (OpenStreetMap — free, no API key needed).
2. Road driving distance is calculated via **OSRM** (free, open-source routing engine).
3. If OSRM is unreachable, the backend falls back to **Haversine straight-line × 1.3** road correction.
4. The distance is applied to the platform's pricing formula:

```
estimated_cost = (base_rate + distance_km × distance_surcharge_per_km) × priority_multiplier
```

### Priority Multipliers (configured in Admin → Platform Settings)

| `cargo_priority` | Default Multiplier |
|---|---|
| `standard` | 1.0× |
| `express` | 1.5× |
| `same_day` | 2.0× |

### Request
```json
{
  "pickup_address":   "Kano City, Kano State",
  "delivery_address": "Mile 12 Market, Lagos",
  "cargo_priority":   "express"
}
```

### Response
```json
{
  "success": true,
  "message": "Cost estimate calculated successfully.",
  "data": {
    "estimated_cost":      93937.5,
    "base_rate":           15000.0,
    "distance_charge":     47625.0,
    "distance_km":         1058.33,
    "priority_multiplier": 1.5,
    "cargo_priority":      "express",
    "pickup_address":      "Kano City, Kano State",
    "delivery_address":    "Mile 12 Market, Lagos",
    "distance_method":     "osrm"
  }
}
```

| Field | Description |
|---|---|
| `distance_method` | `"osrm"` = real road routing \| `"haversine"` = straight-line fallback |
| `distance_km` | Calculated road distance in kilometres |
| `distance_charge` | `distance_km × distance_surcharge_per_km` |
| `estimated_cost` | Final billable estimate after multiplier |

> **Error Handling:** If an address can't be geocoded, the API returns `400` with a descriptive message. If the geocoding service is completely down, it returns `503`. The frontend should always handle both gracefully.

---

## Appendix: Response Envelope

All API responses follow this consistent structure, making it easy for the frontend to handle errors globally:

```json
{
  "success": true,
  "message": "Human readable status message",
  "data": { },
  "errors": {
    "field_name": ["Specific validation error"]
  }
}
```

> `data` is omitted on error responses. `errors` is omitted on success responses.

---

## Appendix: Order Status Flow

```
new_request → assigned → pending_pickup → in_transit → delivered → completed
                                                     ↑
                                          (location updates append here
                                           as extra events, not new statuses)
```

Any status can transition to `cancelled` at any point.

---

## Appendix: Key Business Rules

| Rule | Detail |
|---|---|
| Driver double-booking | A driver already on an active trip cannot be assigned to another. Returns `400` with `driver_id` error. |
| Vehicle double-booking | Same rule for vehicles — one active trip at a time. Returns `400` with `vehicle_id` error. |
| Rating once per order | Each completed order can be rated exactly once. Subsequent attempts return `400`. |
| Rating range | Must be an integer 1–5. Enforced at both serializer and DB (`CheckConstraint`) level. |
| POD required for completion | An order cannot be set to `completed` without a `proof_of_delivery` image. |
| Chat access control | Only the sender and the assigned dispatcher (or an admin) can view or send messages on an order. |
