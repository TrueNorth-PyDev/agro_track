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

---

## 4. Transit & Live Tracking

Once the truck leaves the farm, the dispatcher tracks it through the system.

### Updating Status & Location
**`PATCH /orders/{id}/`**

As the journey progresses, the dispatcher updates the location and status:
1. `{"status": "pending_pickup"}` → Timeline logs **"Pickup Confirmed"**.
2. `{"status": "in_transit", "current_location": "Leaving Ota"}` → Timeline logs **"In Transit"** and the checklist advances.
3. `{"current_location": "Approaching Lagos"}` → Timeline logs an additional **"Location Update"** breadcrumb. The step checklist stays at "In Transit" but updates the description to the latest location.
4. `{"status": "delivered"}` → Timeline logs **"Delivered"**.

### Viewing the Journey Tracker
**`GET /orders/{id}/timeline/`**

Returns the timeline in two distinct structures for the UI:
1. **`checklist`**: A fixed 6-step progress indicator (`Order Placed`, `Dispatcher Assigned`, `Pickup Confirmed`, `In Transit`, `Delivered`, `Completed`). Each step has a `state` (`completed`, `current`, `pending`). This is used to render the top-level progress bar.
2. **`events`**: The raw, chronological log of all events, including every single location update breadcrumb. This is used to render the scrollable history below the checklist.

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
      // ... other steps omitted for brevity
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

*UI Tip: Map over `data.checklist` to build your 6-step progress bar (switch on `item.state` to pick the correct icon). Map over `data.events` to build the scrollable historical log underneath.*

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

### Fetching the Thread
**`GET /orders/{id}/messages/`**

Returns the chat history, the number of unread messages, and `chat_info` identifying the other party (with their initials for UI avatars). Access is strictly limited to the sender and the assigned dispatcher.

### Sending a Message
**`POST /orders/{id}/messages/`**
```json
{
  "content": "Is the truck delayed by the rain?"
}
```

### Reading Messages
**`POST /orders/{id}/messages/read/`**
When the user opens the chat UI, call this endpoint. It bulk-updates all incoming messages from the other party to `is_read = true`, clearing the unread badge.

---

## 6. Proof of Delivery (Completion)

When the goods arrive and are signed for, the dispatcher uploads the signed waybill to close out the order.

### Uploading the POD
**`PATCH /orders/{id}/`** *(Must be sent as `multipart/form-data`)*

- Set `status` to `completed`
- Attach the image file to the `proof_of_delivery` field.

**What happens:**
- The image is saved to the configured AWS S3 bucket.
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
- **Global Settings**: Configure platform-wide rules via the singleton settings `PATCH /admin/settings/`.
- **Deep Analytics**: Fetch revenue graphs, regional distribution, and user acquisition metrics (`GET /admin/analytics/`).

---

## Appendix: Response Envelope

All API responses follow this consistent structure, making it easy for the frontend to handle errors globally:

```json
{
  "success": true, // or false
  "message": "Human readable status message",
  "data": { ... }, // Omitted on error
  "errors": {      // Omitted on success
    "field_name": ["Specific validation error"]
  }
}
```
