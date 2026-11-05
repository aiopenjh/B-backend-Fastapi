from reservation.domain.reservation import Reservation, ReservationStatus

def to_reservation(model):
    return Reservation(
        id=model.id,
        user_id=model.user_id,
        slot_id=model.slot_id,
        party_size=model.party_size,
        contact_phone=model.contact_phone,
        status=ReservationStatus(model.status),
        created_at=model.created_at,
        cancelled_at=model.cancelled_at
    )